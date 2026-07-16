from core import syntax
from core.syntax import (
    STATE_BLOCK_COMMENT,
    STATE_HTML_COMMENT,
    STATE_NONE,
    STATE_TRIPLE_DOUBLE,
    detect_language,
    highlight_line,
    normalize_language,
)


def kinds_at(line, language, state=STATE_NONE):
    spans, next_state = highlight_line(line, language, state)
    return {(line[start:start + length], kind) for start, length, kind in spans}, next_state


# Language detection

def test_detects_php():
    code = (
        "if ( ! isset( $GLOBALS['queue'] ) || ! is_array( $GLOBALS['queue'] ) ) {\n"
        "    $GLOBALS['queue'] = [];\n"
        "}\n"
        "$parent_id = (int) wp_get_post_parent_id( $product_id );"
    )
    assert detect_language(code) == "php"


def test_detects_python():
    assert detect_language("def main():\n    import os\n    print(os.name)") == "python"


def test_detects_javascript():
    assert detect_language("const x = items.map(i => i.id);\nconsole.log(x);") == "javascript"


def test_detects_html():
    assert detect_language('<div class="row">\n  <p>Hello</p>\n</div>') == "html"


def test_detects_css():
    assert detect_language(".card {\n  color: #fff;\n  margin: 4px;\n}") == "css"


def test_detects_sql():
    assert detect_language("SELECT id, name FROM users WHERE active = 1;") == "sql"


def test_unclear_text_detects_nothing():
    assert detect_language("hello") == ""


def test_normalize_language_aliases():
    assert normalize_language("py") == "python"
    assert normalize_language("TS") == "javascript"
    assert normalize_language("c++") == "c"
    assert normalize_language("unknown-lang") == ""


# Tokenisation

def test_php_tokens():
    tokens, state = kinds_at("$id = strlen( $name ); // done", "php")
    assert ("$id", syntax.VARIABLE) in tokens
    assert ("strlen", syntax.BUILTIN) in tokens
    assert ("// done", syntax.COMMENT) in tokens
    assert state == STATE_NONE


def test_python_keyword_string_and_function():
    tokens, _ = kinds_at('def greet(name): return "hi"', "python")
    assert ("def", syntax.KEYWORD) in tokens
    assert ("greet", syntax.FUNCTION) in tokens
    assert ('"hi"', syntax.STRING) in tokens


def test_python_triple_string_spans_lines():
    _, state = highlight_line('text = """docstring start', "python")
    assert state == STATE_TRIPLE_DOUBLE
    spans, state = highlight_line("still inside", "python", state)
    assert spans == [(0, len("still inside"), syntax.STRING)]
    assert state == STATE_TRIPLE_DOUBLE
    spans, state = highlight_line('end"""', "python", state)
    assert state == STATE_NONE


def test_block_comment_spans_lines():
    _, state = highlight_line("/* comment opens", "javascript")
    assert state == STATE_BLOCK_COMMENT
    spans, state = highlight_line("closes here */ let x = 1", "javascript", state)
    assert state == STATE_NONE
    assert (0, len("closes here */"), syntax.COMMENT) in spans


def test_escaped_quote_stays_inside_string():
    tokens, _ = kinds_at(r'x = "a \" b"', "python")
    assert (r'"a \" b"', syntax.STRING) in tokens


def test_sql_case_insensitive_keywords():
    tokens, _ = kinds_at("select id from users", "sql")
    assert ("select", syntax.KEYWORD) in tokens
    assert ("from", syntax.KEYWORD) in tokens


def test_html_tags_attributes_and_comment_state():
    tokens, _ = kinds_at('<div class="row">', "html")
    assert ("<div", syntax.TAG) in tokens
    assert ("class", syntax.ATTRIBUTE) in tokens
    assert ('"row"', syntax.STRING) in tokens
    _, state = highlight_line("<!-- open comment", "html")
    assert state == STATE_HTML_COMMENT


def test_css_property_and_hex_color():
    tokens, _ = kinds_at("  color: #ff8800;", "css")
    assert ("color", syntax.PROPERTY) in tokens
    assert ("#ff8800", syntax.NUMBER) in tokens


def test_json_property_names():
    tokens, _ = kinds_at('  "name": "value",', "json")
    assert ('"name"', syntax.PROPERTY) in tokens
    assert ('"value"', syntax.STRING) in tokens


def test_unknown_language_still_highlights_strings_and_numbers():
    tokens, _ = kinds_at('x "text" 42', "")
    assert ('"text"', syntax.STRING) in tokens
    assert ("42", syntax.NUMBER) in tokens
