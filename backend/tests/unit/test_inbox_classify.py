"""Inbound mailbox classification from versioned .eml fixtures: no network, nothing concluded from absence."""

from pathlib import Path

from services.outreach_os.inbox import classify

FIX = Path(__file__).resolve().parent.parent / "fixtures" / "inbox"


def _c(name):
    return classify((FIX / name).read_bytes())


def test_a_reply_points_at_our_message_and_keeps_only_the_readers_text():
    item = _c("reply.eml")
    assert item.kind == "reply" and item.references == ["orig1@plantiers.com", "orig1@plantiers.com"]
    assert item.excerpt == "Oui, appelez-moi demain."  # the quoted thread (with our unsubscribe link) is dropped
    assert item.inbound_id == "reply1@client.example" and not item.opt_out


def test_a_stop_reply_is_an_opt_out():
    assert _c("reply_stop.eml").opt_out is True


def test_an_auto_reply_is_not_a_reply():
    assert _c("autoreply.eml").kind == "ignore"


def test_a_hard_bounce_names_the_failed_address_and_our_original_message():
    item = _c("bounce_hard.eml")
    assert item.kind == "hard_bounce" and item.failed_recipient == "dead.box@client.example"
    assert item.references == ["orig2@plantiers.com"]


def test_a_temporary_failure_never_suppresses_anything():
    assert _c("bounce_soft.eml").kind == "ignore"


def test_a_message_that_references_nothing_of_ours_is_ignored():
    assert _c("unrelated.eml").kind == "ignore"


def test_garbage_does_not_raise():
    assert classify(b"\x00\xff not an email").kind == "ignore"
    assert classify(b"").kind == "ignore"
