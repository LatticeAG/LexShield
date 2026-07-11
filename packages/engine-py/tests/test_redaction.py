"""Redaction tests per SPEC §9.6."""

from lexshield.redaction import redact_arguments, redact_string


def test_redact_aws_key() -> None:
    text = "credentials AKIAIOSFODNN7EXAMPLE here"
    redacted, applied = redact_string(text)
    assert "[REDACTED_AWS_KEY]" in redacted
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted
    assert applied


def test_redact_openai_api_key() -> None:
    text = "token sk-proj-abcdefghijklmnopqrstuvwxyz123456"
    redacted, applied = redact_string(text)
    assert "[REDACTED_API_KEY]" in redacted
    assert "sk-proj-" not in redacted
    assert applied


def test_redact_bearer_token() -> None:
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig"
    redacted, _ = redact_string(text)
    assert redacted == "Authorization: Bearer [REDACTED]"


def test_redact_password_assignment() -> None:
    text = "config password=supersecret123"
    redacted, _ = redact_string(text)
    assert redacted == "config password=[REDACTED]"


def test_redact_email_hash_default() -> None:
    text = "contact user@example.com please"
    redacted, applied = redact_string(text, redact_emails="hash")
    assert "user@example.com" not in redacted
    assert "[EMAIL_HASH:" in redacted
    assert "email" in applied


def test_redact_arguments_nested() -> None:
    args = {
        "body": "key AKIAIOSFODNN7EXAMPLE",
        "nested": {"token": "Bearer abc.def.ghi"},
    }
    redacted, applied = redact_arguments(args, redact_emails="off")
    assert "[REDACTED_AWS_KEY]" in redacted["body"]
    assert "Bearer [REDACTED]" in redacted["nested"]["token"]
    assert applied
