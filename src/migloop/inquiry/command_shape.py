"""Conservative presentation classification, never filesystem-effect evidence.

Only complete, literal standard-command shapes are classified. Unknown options
for extensible commands, substitutions, redirects, scripts and shell state stay
visible. No evaluation, filesystem access, or read/write graph edges.
"""

import re
import shlex


def read_only_shape(command):
    if not isinstance(command, str) or not command.strip():
        return None
    # Reject shell features before lexing, even when quoted (false negatives are OK).
    if any(c in command for c in "$`\\<>#(){}"):
        return None
    lexer = shlex.shlex(
        command.strip().replace("\n", ";"), posix=True, punctuation_chars=";&|"
    )
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    simple = {
        "cat",
        "grep",
        "head",
        "tail",
        "wc",
        "ls",
        "nl",
        "pwd",
        "cd",
        "echo",
        "true",
        "false",
    }

    def accepted(words):
        if not words:
            return False
        name, *args = words
        if name in simple:
            return True
        # sed's program language can execute or write; allow only literal line-printing.
        return (
            name == "sed"
            and len(args) >= 3
            and args[0] == "-n"
            and re.fullmatch(r"[0-9]+(?:,[0-9]+)?p", args[1]) is not None
            and all(
                path and not path.startswith("-") and not any(c in path for c in "*?[]")
                for path in args[2:]
            )
        )

    commands, words = [], []
    for token in tokens:
        if token and set(token) <= set(";&|"):
            if token not in {";", "&&", "||", "|"} or not accepted(words):
                return None
            commands.append(words[0])
            words = []
        else:
            words.append(token)
    if words:
        if not accepted(words):
            return None
        commands.append(words[0])
    elif not tokens or tokens[-1] != ";":
        return None
    return "standard-command read-only syntax: " + ",".join(sorted(set(commands)))


def call_read_basis(tool, payload):
    if not isinstance(tool, str):
        return None
    name = tool.split(".")[-1].casefold()
    if name in {"read", "read_file", "glob", "grep", "ls", "list_files"}:
        return "native read-only tool contract"
    if name in {"bash", "exec_command", "run_shell_command"} and isinstance(
        payload, dict
    ):
        return read_only_shape(payload.get("command", payload.get("cmd")))
    return None
