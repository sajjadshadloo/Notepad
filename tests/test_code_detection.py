from ui.editor import LARGE_FILE_THRESHOLD, detect_code_blocks


def test_detects_fenced_markdown_code():
    blocks = detect_code_blocks('متن\n```python\nprint("hi")\n```\nادامه')

    assert len(blocks) == 1
    assert blocks[0].fenced
    assert blocks[0].language == "python"
    assert blocks[0].text == 'print("hi")'


def test_detects_common_unfenced_code():
    blocks = detect_code_blocks("def hello():\n    return True")

    assert len(blocks) == 1
    assert blocks[0].start_line == 0
    assert blocks[0].end_line == 1
    assert blocks[0].text == "def hello():\n    return True"


def test_does_not_mark_normal_persian_as_code():
    assert detect_code_blocks("این یک متن عادی فارسی است.") == []


def test_heuristic_disabled_keeps_fenced_blocks_only():
    text = 'def hello():\n    return True\n```js\nlet x = 1\n```'

    blocks = detect_code_blocks(text, heuristic=False)

    # The unfenced def/return is ignored, but the fenced block survives.
    assert len(blocks) == 1
    assert blocks[0].fenced
    assert blocks[0].language == "js"


def test_php_block_is_not_fragmented():
    # Real-world PHP with lone braces and call-only lines must stay one block.
    text = (
        "if ( $tadarok_id === '' ) {\n"
        "    return;\n"
        "}\n"
        "\n"
        "$GLOBALS['queue'][ $product_id ] = $tadarok_id;\n"
        "\n"
        "if ( $post_type === 'product_variation' ) {\n"
        "    $parent_id = (int) wp_get_post_parent_id( $product_id );\n"
        "}"
    )

    blocks = detect_code_blocks(text)

    assert len(blocks) == 1
    assert blocks[0].start_line == 0
    assert blocks[0].end_line == 8
    assert blocks[0].language == "php"


def test_persian_prose_ends_a_code_block():
    text = "x = compute(1)\nprint(x)\nاین توضیح فارسی بعد از کد است\ny = 2"

    blocks = detect_code_blocks(text)

    assert all(not block.contains(2) for block in blocks)


def test_english_prose_is_not_swallowed_by_code():
    text = (
        "const total = items.length;\n"
        "This sentence is a normal note about the code above\n"
        "and it must stay outside of the block"
    )

    blocks = detect_code_blocks(text)

    assert len(blocks) == 1
    assert blocks[0].end_line == 0


def test_unfenced_block_gets_language_detected():
    blocks = detect_code_blocks("def hello():\n    import os\n    print(os)")

    assert len(blocks) == 1
    assert blocks[0].language == "python"


def test_fenced_block_without_tag_gets_language_detected():
    blocks = detect_code_blocks("```\nconst x = 1;\nconsole.log(x);\n```")

    assert len(blocks) == 1
    assert blocks[0].fenced
    assert blocks[0].language == "javascript"


def test_large_text_skips_heuristic_for_responsiveness():
    # A big plain-text file with one code-looking line must not be scanned
    # by the heavy heuristic, so nothing is flagged when it is disabled.
    big_text = ("سطر عادی فارسی\n" * 20_000) + "x == y && a != b"
    assert len(big_text) > LARGE_FILE_THRESHOLD

    assert detect_code_blocks(big_text, heuristic=False) == []
