"""Recognize literal PR creation candidates, without resolving their shell targets.

This is a bounded reader for common shell forms, not a shell interpreter. Quoted
arguments and heredoc data are never searched as executable commands. Known
wrappers are unwrapped only to decide whether to require a separate invocation.
"""
import io
import re
import shlex
from pathlib import PurePosixPath


class CommentLines(io.StringIO):
    """Let shlex discard a comment while preserving its command-ending newline."""
    def readline(self, size=-1):
        line = super().readline(size)
        if line.endswith('\n'):
            self.seek(self.tell() - 1)
            return line[:-1]
        return line


def tokens(source):
    lexer = shlex.shlex(CommentLines(source), posix=False, punctuation_chars=';&|<>()\n')
    lexer.whitespace = ' \t\r'
    lexer.whitespace_split = True
    return list(lexer)


def literal(token):
    parts = shlex.split(token)
    return parts[0] if len(parts) == 1 else token


def without_heredoc_data(source):
    """Remove bodies of ordinary <<WORD/<<'WORD'/<<-WORD, then resume reading."""
    output, header, pending = [], '', []
    for line in source.splitlines(keepends=True):
        if pending:
            delimiter, tabs = pending[0]
            text = line.rstrip('\r\n')
            if (text.lstrip('\t') if tabs else text) == delimiter:
                pending.pop(0)
            output.append('\n')
            continue
        output.append(line)
        header += line
        try:
            parts = tokens(header)
        except ValueError:  # A quoted argument spans lines; don't inspect its contents.
            continue
        for i, token in enumerate(parts[:-1]):
            if token != '<<':
                continue
            word = parts[i + 1]
            tabs = word.startswith('-')
            word = word[1:] if tabs else word
            pending.append((literal(word), tabs))
        header = ''
    return ''.join(output)


ASSIGNMENT = re.compile(r'[A-Za-z_][A-Za-z_0-9]*=')
WRAPPERS = {
    'env': {'-u', '--unset', '-C', '--chdir'},
    'sudo': {'-u', '--user', '-g', '--group', '-h', '--host', '-p', '--prompt', '-C', '-T', '-r', '-t'},
    'time': {'-f', '--format', '-o', '--output'},
    'nohup': set(), 'command': set(), 'exec': {'-a'},
    'xargs': {'-I', '-i', '--replace', '-n', '--max-args', '-L', '--max-lines', '-P', '--max-procs',
              '-s', '--max-chars', '-d', '--delimiter', '-E', '--eof'},
}
SHELLS = {'sh', 'bash', 'dash', 'zsh', 'ksh'}


def command_creates(parts, depth):
    parts = list(parts)
    words = [literal(p) for p in parts]
    while words and (ASSIGNMENT.match(words[0]) or words[0] in ('then', 'do', '!')):
        words.pop(0)
        parts.pop(0)
    if not words:
        return False
    name = PurePosixPath(words[0]).name
    if name == 'gh':
        return words[1:3] == ['pr', 'create']
    if depth >= 8:
        return False
    if name in SHELLS:
        for i, word in enumerate(words[1:], 1):
            if word.startswith('-') and not word.startswith('--') and 'c' in word:
                return i + 1 < len(words) and creates(words[i + 1], depth + 1)
            if not word.startswith('-'):
                break
        return False
    if name == 'command' and any(w in ('-v', '-V') for w in words[1:2]):
        return False  # This mode describes command names without running them.
    if name not in WRAPPERS:
        return False  # echo/grep arguments are data, including an unquoted "gh pr create".
    i = 1
    while i < len(words):
        word = words[i]
        if word == '--':
            i += 1
            break
        if ASSIGNMENT.match(word):
            i += 1
        elif word in WRAPPERS[name]:
            i += 2
        elif word.startswith('-'):
            i += 1  # Includes attached option values, e.g. xargs -I{}.
        else:
            break
    return command_creates(parts[i:], depth + 1)


def creates(source, depth=0):
    try:
        parts = tokens(without_heredoc_data(source))
        command = []
        for part in parts + ['\n']:
            if part and all(c in ';&|()\n' for c in part):
                if command_creates(command, depth):
                    return True
                command = []
            else:
                command.append(part)
    except ValueError:
        # An incomplete literal gh call is still a candidate, but don't scan arbitrary arguments.
        return bool(re.match(r'\s*gh\s+pr\s+create\b', source))
    return False
