from ai_service.qwen_vl.wrapper import _parse_native_boxes


def test_parses_fenced_list_with_prose():
    text = 'Here they are:\n```json\n[\n\t{"bbox_2d": [1, 2, 3, 4], "label": "ship"},\n\t{"bbox_2d": [5, 6, 7, 8], "label": "ship"}\n]\n```'
    assert [o["bbox_2d"] for o in _parse_native_boxes(text)] == [[1, 2, 3, 4], [5, 6, 7, 8]]


def test_keeps_complete_objects_when_truncated():
    text = '[{"bbox_2d": [1, 2, 3, 4], "label": "ship"}, {"bbox_2d": [5, 6'
    assert _parse_native_boxes(text) == [{"bbox_2d": [1, 2, 3, 4], "label": "ship"}]


def test_empty_and_prose_only():
    assert _parse_native_boxes("[]") == []
    assert _parse_native_boxes("There are no aircraft visible.") == []
    assert _parse_native_boxes("") == []
