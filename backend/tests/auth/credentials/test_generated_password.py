"""A generated password meets the server's length, is easy to type and passes the password policy."""

import modules.auth.credentials.password_policy as password_policy


def test_it_is_at_least_24_characters_whatever_the_servers_minimum():
    assert len(password_policy.generate_password(8)) == password_policy.GENERATED_MIN_LENGTH
    assert len(password_policy.generate_password(15)) == password_policy.GENERATED_MIN_LENGTH


def test_it_is_as_long_as_a_longer_minimum_asks():
    assert len(password_policy.generate_password(100)) == 100
    assert len(password_policy.generate_password(128)) == 128


def test_it_uses_only_letters_digits_and_easy_symbols_without_look_alikes():
    alphabet = set(password_policy.GENERATED_CHARACTERS)

    assert alphabet.isdisjoint("0O1lIo")
    assert alphabet - set("ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789") == set("!@#%+=-")
    assert alphabet.isdisjoint("^~`\\|\"' ")
    assert all(set(password_policy.generate_password(40)) <= alphabet for _ in range(50))


def test_it_differs_every_time():
    assert len({password_policy.generate_password(24) for _ in range(100)}) == 100


def test_it_passes_the_password_policy_for_an_account():
    for min_length in (8, 15, 64, 128):
        password = password_policy.generate_password(min_length)

        password_policy.check_password(password, min_length, "alice", "alice@example.com")
