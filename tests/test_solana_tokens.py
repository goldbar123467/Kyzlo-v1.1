from otq.config.solana_tokens import get_token


def test_solana_token_mints_are_correct_for_jupiter_universe() -> None:
    assert get_token("SOL").mint == "So11111111111111111111111111111111111111112"
    assert get_token("USDC").mint == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    assert get_token("JUP").mint == "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"
    assert get_token("BONK").mint == "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
    assert get_token("TRUMP").mint == "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN"


def test_get_token_is_case_insensitive() -> None:
    assert get_token("jup").mint == get_token("JUP").mint
