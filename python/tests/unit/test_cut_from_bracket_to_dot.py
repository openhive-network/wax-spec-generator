import pytest

from api_client_generator._private.common.array_handle import cut_from_bracket_to_dot


@pytest.mark.parametrize(
    "input_str, expected",
    [
        ("list[__main__.SomeAttribute]", "list[SomeAttribute]"),
        (
            "list[condenser_api.condenser_api_description.CondenserBroadcastTransactionItem]",
            "list[CondenserBroadcastTransactionItem]",
        ),
    ],
)
def test_cut_from_bracket_to_dot(input_str, expected):
    assert cut_from_bracket_to_dot(input_str) == expected
