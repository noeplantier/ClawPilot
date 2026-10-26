"""Successful persisted enrichment dispatches the existing qualification task."""

from unittest.mock import patch

from tasks.prospecting_tasks import enrich_task


def test_successful_enrichment_queues_existing_qualification_task():
    with patch("tasks.prospecting_tasks._enrich", return_value=True), patch(
        "tasks.qualification_tasks.score_enriched_leads.apply_async"
    ) as enqueue:
        assert enrich_task("enrichment-job") is True

    enqueue.assert_called_once_with(queue="automation")


def test_enrichment_without_completed_page_does_not_queue_qualification():
    with patch("tasks.prospecting_tasks._enrich", return_value=False), patch(
        "tasks.qualification_tasks.score_enriched_leads.apply_async"
    ) as enqueue:
        assert enrich_task("enrichment-job") is False

    enqueue.assert_not_called()
