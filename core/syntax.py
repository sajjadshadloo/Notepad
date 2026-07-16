"""Language detection and per-line syntax highlighting for code blocks.

Pure logic, no Qt: ``detect_language`` guesses the language of a code
snippet, and ``highlight_line`` tokenises one line into (start, length,
token-kind) spans. Multi-line constructs (block comments, Python triple
strings, HTML comments) survive line breaks through the small integer
state that QSyntaxHighlighter stores per block.
"""
import re
from dataclasses import dataclass, field

# Token kinds — the UI maps these to theme colors.
KEYWORD = "keyword"
BUILTIN = "builtin"
STRING = "string"
COMMENT = "comment"
NUMBER = "number"
FUNCTION = "function"
CLASS = "class"
VARIABLE = "variable"
TAG = "tag"
ATTRIBUTE = "attribute"
PROPERTY = "property"
DECORATOR = "decorator"

# Block states carried between lines (0 must mean "nothing open").
STATE_NONE = 0
STATE_BLOCK_COMMENT = 1
STATE_TRIPLE_SINGLE = 2
STATE_TRIPLE_DOUBLE = 3
STATE_HTML_COMMENT = 4

_WORD_RE = re.compile(r"[A-Za-z_]\w*")
_NUMBER_RE = re.compile(
    r"0[xX][0-9a-fA-F_]+|\d[\d_]*\.?[\d_]*(?:[eE][+-]?\d+)?|\.\d[\d_]*"
)
_VARIABLE_RE = re.compile(r"\$[A-Za-z_]\w*|\$\{\w+\}|\$[0-9#?@*]")
_DECORATOR_RE = re.compile(r"@[\w.]+")
_PREPROCESSOR_RE = re.compile(r"#\s*\w+")


@dataclass(frozen=True)
class LangSpec:
    name: str
    keywords: frozenset = frozenset()
    builtins: frozenset = frozenset()
    line_comments: tuple = ()
    block_comment: tuple | None = None
    strings: tuple = ('"', "'")
    triple_strings: bool = False
    variable_prefix: bool = False  # $name (PHP, Bash)
    decorators: bool = False       # @name (Python)
    preprocessor: bool = False     # #include (C family)
    case_insensitive: bool = False
    classify_capitalized: bool = True  # Capitalized words as class names


def _kw(words: str) -> frozenset:
    return frozenset(words.split())


PYTHON = LangSpec(
    name="python",
    keywords=_kw(
        "def class return if elif else for while try except finally with as "
        "import from pass break continue lambda yield global nonlocal del "
        "raise assert in is not and or async await match case"
    ),
    builtins=_kw(
        "True False None self cls print len range str int float list dict "
        "set tuple bool bytes type object super isinstance issubclass open "
        "enumerate zip map filter sorted reversed sum min max abs round any "
        "all repr hasattr getattr setattr Exception ValueError TypeError "
        "KeyError IndexError RuntimeError StopIteration __init__ __name__"
    ),
    line_comments=("#",),
    triple_strings=True,
    decorators=True,
)

JAVASCRIPT = LangSpec(
    name="javascript",
    keywords=_kw(
        "function var let const if else for while do switch case break "
        "continue return new delete typeof instanceof in of class extends "
        "super import export from default try catch finally throw yield "
        "async await static get set void debugger with "
        "interface type enum implements declare readonly namespace public "
        "private protected abstract any string number boolean never unknown"
    ),
    builtins=_kw(
        "true false null undefined NaN Infinity this arguments console "
        "window document Math JSON Promise Array Object String Number "
        "Boolean Map Set Symbol RegExp Date Error require module exports "
        "globalThis fetch setTimeout setInterval parseInt parseFloat"
    ),
    line_comments=("//",),
    block_comment=("/*", "*/"),
    strings=('"', "'", "`"),
)

PHP = LangSpec(
    name="php",
    keywords=_kw(
        "function if else elseif for foreach while do switch case break "
        "continue return echo print class new extends implements interface "
        "trait public private protected static abstract final const global "
        "require require_once include include_once namespace use as try "
        "catch finally throw instanceof array list and or xor endif "
        "endforeach endwhile endswitch match fn callable clone declare "
        "default enum goto insteadof readonly var yield"
    ),
    builtins=_kw(
        "true false null isset unset empty die exit strlen count array_map "
        "array_filter array_merge array_keys array_values in_array implode "
        "explode str_replace strpos substr sprintf printf trim is_array "
        "is_string is_int is_numeric is_null intval floatval strval "
        "json_encode json_decode define defined function_exists"
    ),
    line_comments=("//", "#"),
    block_comment=("/*", "*/"),
    variable_prefix=True,
)

SQL = LangSpec(
    name="sql",
    keywords=_kw(
        "select from where insert into update delete set values create "
        "table alter drop index view join inner left right full outer on "
        "as and or not null primary key foreign references group by order "
        "having limit offset distinct union all exists between like in is "
        "case when then else end begin commit rollback transaction if "
        "database truncate constraint unique default auto_increment "
        "int integer varchar char text date datetime timestamp decimal "
        "float double boolean blob"
    ),
    builtins=_kw("count sum avg min max now coalesce ifnull concat cast"),
    line_comments=("--", "#"),
    block_comment=("/*", "*/"),
    case_insensitive=True,
    classify_capitalized=False,
)

C_FAMILY = LangSpec(
    name="c",
    keywords=_kw(
        "int long short char float double void unsigned signed bool struct "
        "union enum typedef const static extern volatile register inline if "
        "else for while do switch case default break continue return goto "
        "sizeof new delete class public private protected virtual override "
        "template typename namespace using try catch throw operator friend "
        "constexpr auto decltype mutable explicit final abstract interface "
        "implements extends package synchronized transient instanceof var "
        "out ref readonly sealed internal base async await string object "
        "decimal byte uint ulong ushort partial where get set yield lock is "
        "as import module"
    ),
    builtins=_kw(
        "true false null nullptr NULL this printf scanf malloc free std "
        "cout cin endl vector map String System Console Math Integer "
        "Boolean Exception List Dictionary Task"
    ),
    line_comments=("//",),
    block_comment=("/*", "*/"),
    preprocessor=True,
)

BASH = LangSpec(
    name="bash",
    keywords=_kw(
        "if then else elif fi for in do done while until case esac function "
        "return exit local export readonly declare shift break continue "
        "select time coproc"
    ),
    builtins=_kw(
        "echo printf cd ls grep sed awk cat rm mv cp mkdir touch chmod "
        "chown curl wget sudo apt yum git docker python pip node npm test "
        "set unset source eval exec trap kill sleep find xargs tar head tail"
    ),
    line_comments=("#",),
    variable_prefix=True,
    classify_capitalized=False,
)

JSON_SPEC = LangSpec(
    name="json",
    builtins=_kw("true false null"),
    strings=('"',),
    classify_capitalized=False,
)

GENERIC = LangSpec(
    name="generic",
    line_comments=("//", "#"),
    block_comment=("/*", "*/"),
    classify_capitalized=False,
)

_SPECS = {
    "python": PYTHON,
    "javascript": JAVASCRIPT,
    "php": PHP,
    "sql": SQL,
    "c": C_FAMILY,
    "bash": BASH,
    "json": JSON_SPEC,
}

# Fence tags and common names -> internal language id.
LANGUAGE_ALIASES = {
    "python": "python", "py": "python", "python3": "python",
    "javascript": "javascript", "js": "javascript", "jsx": "javascript",
    "typescript": "javascript", "ts": "javascript", "tsx": "javascript",
    "node": "javascript",
    "php": "php",
    "html": "html", "xml": "html", "svg": "html", "vue": "html",
    "css": "css", "scss": "css", "less": "css",
    "sql": "sql", "mysql": "sql", "postgres": "sql", "sqlite": "sql",
    "json": "json",
    "c": "c", "cpp": "c", "c++": "c", "h": "c", "hpp": "c", "cc": "c",
    "cs": "c", "csharp": "c", "c#": "c", "java": "c", "kotlin": "c",
    "go": "c", "rust": "c", "swift": "c",
    "bash": "bash", "sh": "bash", "shell": "bash", "zsh": "bash",
    "console": "bash", "powershell": "bash", "ps1": "bash",
}


def normalize_language(tag: str) -> str:
    """Map a fence tag or detector output to an internal language id."""
    return LANGUAGE_ALIASES.get((tag or "").strip().lower(), "")


# Language detection: weighted regex evidence over the snippet.

_DETECTORS: dict[str, list[tuple[re.Pattern, int]]] = {
    "php": [
        (re.compile(r"<\?php|<\?="), 10),
        (re.compile(r"\$\w+\s*(?:=|\[|->)"), 3),
        (re.compile(r"->\s*\w+\s*\("), 2),
        (re.compile(r"\becho\s"), 1),
        (re.compile(r"\bfunction\s+\w+\s*\(.*\)\s*\{"), 2),
        (re.compile(r"\$GLOBALS|\$_(?:GET|POST|SERVER|SESSION)"), 5),
        (re.compile(r"\b(?:isset|empty)\s*\(\s*\$"), 4),
    ],
    "python": [
        (re.compile(r"^\s*def\s+\w+\s*\(", re.M), 4),
        (re.compile(r"^\s*(?:import|from)\s+[\w.]+", re.M), 3),
        (re.compile(r"\bself\.\w+"), 3),
        (re.compile(r"^\s*(?:elif|except)\b", re.M), 4),
        (re.compile(r"^\s*(?:if|for|while|with|class)\b[^{;]*:\s*(?:#.*)?$", re.M), 2),
        (re.compile(r"\bprint\s*\("), 1),
        (re.compile(r"f['\"]"), 2),
    ],
    "javascript": [
        (re.compile(r"\b(?:const|let)\s+\w+\s*="), 3),
        (re.compile(r"=>"), 2),
        (re.compile(r"\bconsole\.\w+\s*\("), 4),
        (re.compile(r"===|!=="), 2),
        (re.compile(r"\bfunction\s*\w*\s*\("), 1),
        (re.compile(r"\bdocument\.\w+|\bwindow\.\w+"), 3),
        (re.compile(r"\brequire\s*\(|\bimport\s+.*\bfrom\s+['\"]"), 3),
    ],
    "html": [
        (re.compile(r"<!DOCTYPE", re.I), 10),
        (re.compile(r"</?(?:div|span|p|a|html|body|head|script|style|img|ul|ol|li|table|tr|td|h[1-6]|form|input|button|nav|section|header|footer|meta|link)\b", re.I), 3),
        (re.compile(r"</\w+>"), 2),
        (re.compile(r"<\w+[^>]*/>"), 2),
    ],
    "css": [
        (re.compile(r"@(?:media|import|keyframes|font-face|charset)\b"), 5),
        (re.compile(r"^\s*[.#]?[\w-]+(?:\s*[,>+~]\s*[.#]?[\w-]+)*\s*\{", re.M), 3),
        (re.compile(r"[\w-]+\s*:\s*[^;{}]+;", re.M), 2),
        (re.compile(r"#[0-9a-fA-F]{3,8}\b"), 1),
        (re.compile(r"\b\d+(?:px|em|rem|vh|vw|%)\b"), 2),
    ],
    "sql": [
        (re.compile(r"\bSELECT\b[\s\S]*?\bFROM\b", re.I), 6),
        (re.compile(r"\bINSERT\s+INTO\b", re.I), 6),
        (re.compile(r"\bUPDATE\b[\s\S]*?\bSET\b", re.I), 5),
        (re.compile(r"\bCREATE\s+(?:TABLE|INDEX|VIEW|DATABASE)\b", re.I), 6),
        (re.compile(r"\b(?:WHERE|ORDER\s+BY|GROUP\s+BY|LEFT\s+JOIN)\b", re.I), 2),
    ],
    "json": [
        (re.compile(r"^\s*[{\[]\s*$", re.M), 2),
        (re.compile(r"\"[\w-]+\"\s*:"), 2),
        (re.compile(r":\s*(?:true|false|null)\b"), 2),
    ],
    "c": [
        (re.compile(r"#\s*include\s*[<\"]"), 8),
        (re.compile(r"\bstd::\w+"), 5),
        (re.compile(r"\bint\s+main\s*\("), 6),
        (re.compile(r"\bprintf\s*\(|\bcout\s*<<"), 4),
        (re.compile(r"\bpublic\s+(?:class|static|void)\b"), 4),
        (re.compile(r"\busing\s+System\b|\bimport\s+java\b"), 8),
        (re.compile(r"\bConsole\.Write|\bSystem\.out\.print"), 6),
    ],
    "bash": [
        (re.compile(r"^#!.*\b(?:bash|sh|zsh)\b"), 10),
        (re.compile(r"^\s*(?:fi|esac|done)\s*$", re.M), 5),
        (re.compile(r"\becho\s+[\"$]"), 2),
        (re.compile(r"\$\{\w+\}|\$\(\w"), 2),
        (re.compile(r"^\s*(?:sudo|apt|git|curl|wget|docker)\s+\w", re.M), 3),
    ],
}


def detect_language(text: str) -> str:
    """Best-effort language guess for a code snippet ('' when unclear)."""
    sample = text[:4000]
    if not sample.strip():
        return ""
    best_language = ""
    best_score = 0
    for language, patterns in _DETECTORS.items():
        score = 0
        for pattern, weight in patterns:
            hits = len(pattern.findall(sample))
            if hits:
                score += min(hits, 5) * weight
        if score > best_score:
            best_language, best_score = language, score
    # JSON braces alone are weak evidence next to real JS/PHP signals.
    return best_language if best_score >= 4 else ""


# Tokenisers

def highlight_line(line: str, language: str, state: int = STATE_NONE):
    """Tokenise one line.

    Returns ``(spans, next_state)`` where spans are ``(start, length,
    kind)`` and ``next_state`` is the block state to carry into the next
    line (0 when nothing is left open).
    """
    if language == "html":
        return _highlight_html(line, state)
    if language == "css":
        return _highlight_css(line, state)
    spec = _SPECS.get(language, GENERIC)
    return _highlight_generic(line, spec, state)


def _scan_string(line: str, start: int, quote: str) -> int:
    """End index (exclusive) of a quoted string starting at ``start``."""
    i = start + 1
    n = len(line)
    while i < n:
        if line[i] == "\\":
            i += 2
            continue
        if line[i] == quote:
            return i + 1
        i += 1
    return n


def _highlight_generic(line: str, spec: LangSpec, state: int):
    spans: list[tuple[int, int, str]] = []
    n = len(line)
    i = 0

    if state == STATE_BLOCK_COMMENT and spec.block_comment:
        close = spec.block_comment[1]
        end = line.find(close)
        if end == -1:
            spans.append((0, n, COMMENT))
            return spans, STATE_BLOCK_COMMENT
        i = end + len(close)
        spans.append((0, i, COMMENT))
    elif state in (STATE_TRIPLE_SINGLE, STATE_TRIPLE_DOUBLE):
        quote = "'''" if state == STATE_TRIPLE_SINGLE else '"""'
        end = line.find(quote)
        if end == -1:
            spans.append((0, n, STRING))
            return spans, state
        i = end + 3
        spans.append((0, i, STRING))

    while i < n:
        ch = line[i]
        if ch in " \t":
            i += 1
            continue

        line_comment = next(
            (lc for lc in spec.line_comments if line.startswith(lc, i)), None
        )
        if line_comment is not None:
            spans.append((i, n - i, COMMENT))
            return spans, STATE_NONE

        if spec.block_comment and line.startswith(spec.block_comment[0], i):
            close = spec.block_comment[1]
            end = line.find(close, i + len(spec.block_comment[0]))
            if end == -1:
                spans.append((i, n - i, COMMENT))
                return spans, STATE_BLOCK_COMMENT
            end += len(close)
            spans.append((i, end - i, COMMENT))
            i = end
            continue

        if spec.triple_strings and line.startswith(('"""', "'''"), i):
            quote = line[i] * 3
            end = line.find(quote, i + 3)
            if end == -1:
                spans.append((i, n - i, STRING))
                return spans, (
                    STATE_TRIPLE_DOUBLE if quote == '"""' else STATE_TRIPLE_SINGLE
                )
            spans.append((i, end + 3 - i, STRING))
            i = end + 3
            continue

        if ch in spec.strings:
            end = _scan_string(line, i, ch)
            kind = STRING
            if spec.name == "json":
                after = end
                while after < n and line[after] in " \t":
                    after += 1
                if after < n and line[after] == ":":
                    kind = PROPERTY
            spans.append((i, end - i, kind))
            i = end
            continue

        if ch.isdigit() or (ch == "." and i + 1 < n and line[i + 1].isdigit()):
            match = _NUMBER_RE.match(line, i)
            if match:
                spans.append((i, match.end() - i, NUMBER))
                i = match.end()
                continue

        if spec.variable_prefix and ch == "$":
            match = _VARIABLE_RE.match(line, i)
            if match:
                spans.append((i, match.end() - i, VARIABLE))
                i = match.end()
                continue

        if spec.decorators and ch == "@":
            match = _DECORATOR_RE.match(line, i)
            if match:
                spans.append((i, match.end() - i, DECORATOR))
                i = match.end()
                continue

        if spec.preprocessor and ch == "#" and not line[:i].strip():
            match = _PREPROCESSOR_RE.match(line, i)
            if match:
                spans.append((i, match.end() - i, KEYWORD))
                i = match.end()
                continue

        if ch.isalpha() or ch == "_":
            match = _WORD_RE.match(line, i)
            word = match.group()
            lookup = word.lower() if spec.case_insensitive else word
            after = match.end()
            while after < n and line[after] in " \t":
                after += 1
            if lookup in spec.keywords:
                kind = KEYWORD
            elif lookup in spec.builtins:
                kind = BUILTIN
            elif after < n and line[after] == "(":
                kind = FUNCTION
            elif (
                spec.classify_capitalized
                and word[0].isupper()
                and any(c.islower() for c in word)
            ):
                kind = CLASS
            else:
                kind = None
            if kind:
                spans.append((i, match.end() - i, kind))
            i = match.end()
            continue

        i += 1

    return spans, STATE_NONE


_HTML_TAG_RE = re.compile(r"</?\s*([\w-]+)")
_HTML_ATTR_RE = re.compile(r"([\w-]+)(\s*=\s*)?")


def _highlight_html(line: str, state: int):
    spans: list[tuple[int, int, str]] = []
    n = len(line)
    i = 0

    if state == STATE_HTML_COMMENT:
        end = line.find("-->")
        if end == -1:
            spans.append((0, n, COMMENT))
            return spans, STATE_HTML_COMMENT
        i = end + 3
        spans.append((0, i, COMMENT))

    while i < n:
        ch = line[i]
        if line.startswith("<!--", i):
            end = line.find("-->", i + 4)
            if end == -1:
                spans.append((i, n - i, COMMENT))
                return spans, STATE_HTML_COMMENT
            end += 3
            spans.append((i, end - i, COMMENT))
            i = end
            continue
        if ch == "<":
            tag = _HTML_TAG_RE.match(line, i)
            if tag or line.startswith("<!", i) or line.startswith("<?", i):
                tag_end = tag.end() if tag else i + 2
                spans.append((i, tag_end - i, TAG))
                i = tag_end
                # Attributes until the closing '>'
                close = line.find(">", i)
                limit = close if close != -1 else n
                j = i
                while j < limit:
                    cj = line[j]
                    if cj in "\"'":
                        end = _scan_string(line, j, cj)
                        end = min(end, limit)
                        spans.append((j, end - j, STRING))
                        j = end
                        continue
                    if cj.isalpha():
                        attr = _HTML_ATTR_RE.match(line, j)
                        if attr:
                            spans.append((j, len(attr.group(1)), ATTRIBUTE))
                            j = attr.end()
                            continue
                    j += 1
                if close != -1:
                    spans.append((close, 1, TAG))
                    i = close + 1
                else:
                    i = n
                continue
        if ch == ">":
            spans.append((i, 1, TAG))
            i += 1
            continue
        if ch == "&":
            entity = re.match(r"&#?\w+;", line[i:])
            if entity:
                spans.append((i, entity.end(), NUMBER))
                i += entity.end()
                continue
        i += 1

    return spans, STATE_NONE


_CSS_AT_RE = re.compile(r"@[\w-]+")
_CSS_PROPERTY_RE = re.compile(r"[\w-]+(?=\s*:)")
_CSS_HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_CSS_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?(?:px|em|rem|vh|vw|vmin|vmax|s|ms|deg|fr|%)?")
_CSS_SELECTOR_RE = re.compile(r"[.#][\w-]+")


def _highlight_css(line: str, state: int):
    spans: list[tuple[int, int, str]] = []
    n = len(line)
    i = 0

    if state == STATE_BLOCK_COMMENT:
        end = line.find("*/")
        if end == -1:
            spans.append((0, n, COMMENT))
            return spans, STATE_BLOCK_COMMENT
        i = end + 2
        spans.append((0, i, COMMENT))

    while i < n:
        ch = line[i]
        if line.startswith("/*", i):
            end = line.find("*/", i + 2)
            if end == -1:
                spans.append((i, n - i, COMMENT))
                return spans, STATE_BLOCK_COMMENT
            end += 2
            spans.append((i, end - i, COMMENT))
            i = end
            continue
        if ch in "\"'":
            end = _scan_string(line, i, ch)
            spans.append((i, end - i, STRING))
            i = end
            continue
        if ch == "@":
            match = _CSS_AT_RE.match(line, i)
            if match:
                spans.append((i, match.end() - i, KEYWORD))
                i = match.end()
                continue
        if ch == "#":
            match = _CSS_HEX_RE.match(line, i)
            if match:
                spans.append((i, match.end() - i, NUMBER))
                i = match.end()
                continue
            match = _CSS_SELECTOR_RE.match(line, i)
            if match:
                spans.append((i, match.end() - i, CLASS))
                i = match.end()
                continue
        if ch == ".":
            match = _CSS_SELECTOR_RE.match(line, i)
            if match:
                spans.append((i, match.end() - i, CLASS))
                i = match.end()
                continue
        if ch == "!":
            if line.startswith("!important", i):
                spans.append((i, len("!important"), KEYWORD))
                i += len("!important")
                continue
        if ch.isdigit():
            match = _CSS_NUMBER_RE.match(line, i)
            if match:
                spans.append((i, match.end() - i, NUMBER))
                i = match.end()
                continue
        if ch.isalpha() or ch == "-":
            match = _CSS_PROPERTY_RE.match(line, i)
            if match:
                spans.append((i, match.end() - i, PROPERTY))
                i = match.end()
                continue
            word = re.match(r"[\w-]+", line[i:])
            i += word.end() if word else 1
            continue
        i += 1

    return spans, STATE_NONE
