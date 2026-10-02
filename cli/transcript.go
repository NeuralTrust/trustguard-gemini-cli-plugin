package main

import (
	"bytes"
	"encoding/json"
	"os"
	"regexp"
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

// readTranscriptTurn reads at most the last 8 MiB of path.
func readTranscriptTurn(path string) transcriptTurn {
	if strings.TrimSpace(path) == "" {
		return transcriptTurn{}
	}
	f, err := os.Open(path)
	if err != nil {
		return transcriptTurn{}
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil {
		return transcriptTurn{}
	}
	size := info.Size()
	start := int64(0)
	if size > transcriptTailBytes {
		start = size - transcriptTailBytes
	}
	if _, err := f.Seek(start, 0); err != nil {
		return transcriptTurn{}
	}
	buf := make([]byte, size-start)
	n, err := f.Read(buf)
	if n == 0 || (err != nil && n == 0) {
		return transcriptTurn{}
	}
	buf = buf[:n]
	if start > 0 {
		if i := bytes.IndexByte(buf, '\n'); i >= 0 {
			buf = buf[i+1:]
		}
	}

	var turn transcriptTurn
	for _, line := range bytes.Split(buf, []byte("\n")) {
		line = bytes.TrimSpace(line)
		if len(line) == 0 {
			continue
		}
		kind, text := classifyTranscriptLine(line)
		switch kind {
		case "USER_INPUT":
			turn.ok = true
			if text != "" {
				turn.prompt = text
			}
			turn.promptPending = true
			turn.replyReady = false
		case "PLANNER_RESPONSE":
			turn.ok = true
			if text != "" {
				turn.reply = text
			}
			turn.promptPending = false
			turn.replyReady = strings.TrimSpace(turn.reply) != ""
		}
	}
	return turn
}

func classifyTranscriptLine(line []byte) (string, string) {
	var obj map[string]any
	if err := json.Unmarshal(line, &obj); err != nil {
		return "", ""
	}
	kind := stepKind(obj)
	text := ""
	if m := userRequestRE.FindStringSubmatch(string(line)); len(m) == 2 {
		text = strings.TrimSpace(m[1])
	}
	if kind == "PLANNER_RESPONSE" {
		if body := stepBody(obj); body != "" {
			text = body
		}
	}
	if kind == "USER_INPUT" && text == "" {
		text = stepBody(obj)
	}
	return kind, text
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
