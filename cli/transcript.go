package main

import (
	"bytes"
	"encoding/json"
	"io"
	"os"
	"regexp"
	"strconv"
	"strings"
)

const transcriptTailBytes = 8 << 20

var userRequestRE = regexp.MustCompile(`(?s)<USER_REQUEST>(.*?)</USER_REQUEST>`)

// transcriptTurn is the latest user turn in an Antigravity JSONL transcript.
// The file format is not a public contract; callers fall back when ok is false.
type transcriptTurn struct {
	prompt        string
	reply         string
	promptPending bool
	replyReady    bool
	ok            bool
}

func transcriptPathOf(in hookInput) string {
	if p := strings.TrimSpace(in.TranscriptPathAG); p != "" {
		return p
	}
	return strings.TrimSpace(in.TranscriptPath)
}

// readTranscriptSteps decodes the steps in at most the last 8 MiB of path,
// skipping lines that are not JSON objects. A missing file yields nil.
func readTranscriptSteps(path string) []map[string]any {
	if strings.TrimSpace(path) == "" {
		return nil
	}
	f, err := os.Open(path)
	if err != nil {
		return nil
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil {
		return nil
	}
	size := info.Size()
	start := int64(0)
	if size > transcriptTailBytes {
		start = size - transcriptTailBytes
	}
	if _, err := f.Seek(start, 0); err != nil {
		return nil
	}
	buf := make([]byte, size-start)
	n, _ := io.ReadFull(f, buf)
	if n == 0 {
		return nil
	}
	buf = buf[:n]
	if start > 0 {
		if i := bytes.IndexByte(buf, '\n'); i >= 0 {
			buf = buf[i+1:]
		}
	}

	var steps []map[string]any
	for _, line := range bytes.Split(buf, []byte("\n")) {
		line = bytes.TrimSpace(line)
		if len(line) == 0 {
			continue
		}
		var obj map[string]any
		if err := json.Unmarshal(line, &obj); err != nil || obj == nil {
			continue
		}
		steps = append(steps, obj)
	}
	return steps
}

// readTranscriptTurn returns the latest user turn. reply is the text of the
// latest PLANNER_RESPONSE in that turn; a response that only calls tools has
// none, so replyReady is false until the model writes text.
func readTranscriptTurn(path string) transcriptTurn {
	var turn transcriptTurn
	for _, obj := range readTranscriptSteps(path) {
		switch stepKind(obj) {
		case "USER_INPUT":
			turn.ok = true
			turn.prompt = stepBody(obj)
			turn.promptPending = true
			turn.reply = ""
			turn.replyReady = false
		case "PLANNER_RESPONSE":
			turn.ok = true
			turn.reply = stepBody(obj)
			turn.promptPending = false
			turn.replyReady = turn.reply != ""
		}
	}
	return turn
}

// readToolStepOutput returns what the tool step at stepIdx produced: its error
// when it failed, otherwise its content without Antigravity's timing header.
// Antigravity's PostToolUse payload carries no result, only stepIdx.
func readToolStepOutput(path string, stepIdx int) string {
	steps := readTranscriptSteps(path)
	for i := len(steps) - 1; i >= 0; i-- {
		if idx, ok := stepIndex(steps[i]); !ok || idx != stepIdx {
			continue
		}
		if msg, _ := steps[i]["error"].(string); strings.TrimSpace(msg) != "" {
			return strings.TrimSpace(msg)
		}
		content, _ := steps[i]["content"].(string)
		return stripStepHeader(content)
	}
	return ""
}

func stepIndex(obj map[string]any) (int, bool) {
	switch v := obj["step_index"].(type) {
	case float64:
		return int(v), true
	case string:
		n, err := strconv.Atoi(strings.TrimSpace(v))
		return n, err == nil
	}
	return 0, false
}

// stripStepHeader drops the "Created At:" / "Completed At:" lines Antigravity
// puts before a tool step's output.
func stripStepHeader(content string) string {
	lines := strings.Split(content, "\n")
	i := 0
	for i < len(lines) {
		line := strings.TrimSpace(lines[i])
		if line == "" || strings.HasPrefix(line, "Created At:") || strings.HasPrefix(line, "Completed At:") {
			i++
			continue
		}
		break
	}
	return strings.TrimSpace(strings.Join(lines[i:], "\n"))
}

func stepKind(obj map[string]any) string {
	for _, key := range []string{"type", "stepType", "kind", "step", "name", "role"} {
		switch v := obj[key].(type) {
		case string:
			switch strings.ToUpper(strings.TrimSpace(v)) {
			case "USER_INPUT", "PLANNER_RESPONSE":
				return strings.ToUpper(strings.TrimSpace(v))
			}
		case map[string]any:
			if kind := stepKind(v); kind != "" {
				return kind
			}
		}
	}
	return ""
}

func stepBody(obj map[string]any) string {
	for _, key := range []string{"text", "message", "response", "output", "content"} {
		switch v := obj[key].(type) {
		case string:
			s := strings.TrimSpace(v)
			if s == "" || strings.EqualFold(s, "PLANNER_RESPONSE") || strings.EqualFold(s, "USER_INPUT") {
				continue
			}
			if m := userRequestRE.FindStringSubmatch(s); len(m) == 2 {
				return strings.TrimSpace(m[1])
			}
			return s
		}
	}
	return ""
}

// overwriteArgs is the tool-arg patch Antigravity shallow-merges on decision overwrite.
func overwriteArgs(in hookInput, payload map[string]any) map[string]any {
	if len(payload) == 0 {
		return nil
	}
	if _, ok := payload["CommandLine"]; ok {
		return payload
	}
	if cmd, ok := payload["input"].(string); ok && strings.TrimSpace(cmd) != "" && in.ToolName == antigravityShellTool {
		return map[string]any{"CommandLine": cmd}
	}
	if cmd, ok := payload["command"].(string); ok && strings.TrimSpace(cmd) != "" && in.ToolName == antigravityShellTool {
		return map[string]any{"CommandLine": cmd}
	}
	return nil
}
