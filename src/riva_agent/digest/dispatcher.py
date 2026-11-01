import logging
import shutil
import subprocess

from riva_agent.digest.models import DigestConfig, DigestRecord, NotificationResult

logger = logging.getLogger(__name__)

# Typical comfortable limit for a single Signal text bubble
SIGNAL_CHUNK_MAX_CHARS = 3800


def _split_text_chunks(text: str, max_chars: int = SIGNAL_CHUNK_MAX_CHARS) -> list[str]:
    """Split long text into multiple chunks while preserving paragraph boundaries when possible."""
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    paragraphs = text.split("\n\n")
    for para in paragraphs:
        para_len = len(para) + 2
        if current_len + para_len > max_chars and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [para]
            current_len = para_len
        else:
            current_chunk.append(para)
            current_len += para_len

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    # Fallback if a single paragraph exceeded max_chars
    final_chunks: list[str] = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            final_chunks.append(chunk)
        else:
            for i in range(0, len(chunk), max_chars):
                final_chunks.append(chunk[i : i + max_chars])

    return final_chunks


def send_signal_message(
    recipient: str,
    message: str,
    *,
    dry_run: bool = False,
    timeout: float = 30.0,
) -> NotificationResult:
    """Send an E2EE message over Signal using OpenClaw's CLI bridge."""
    if not recipient or not recipient.strip():
        return NotificationResult(
            channel="signal",
            success=False,
            message="No Signal recipient specified.",
            error="Recipient is empty or unconfigured",
        )

    clean_recipient = recipient.strip()
    chunks = _split_text_chunks(message)

    if dry_run:
        return NotificationResult(
            channel="signal",
            success=True,
            message=(
                f"[dry-run] Would send {len(chunks)} chunk(s) "
                f"({len(message)} chars) to Signal recipient {clean_recipient}"
            ),
        )

    openclaw_bin = shutil.which("openclaw")
    if not openclaw_bin:
        err_msg = "openclaw CLI executable not found in PATH."
        logger.error(err_msg)
        return NotificationResult(
            channel="signal",
            success=False,
            message=err_msg,
            error="openclaw_not_found",
        )

    sent_count = 0
    for idx, chunk in enumerate(chunks, 1):
        prefix = f"({idx}/{len(chunks)})\n\n" if len(chunks) > 1 else ""
        payload = f"{prefix}{chunk}"

        cmd = [
            openclaw_bin,
            "message",
            "send",
            "--channel",
            "signal",
            "--target",
            clean_recipient,
            "--message",
            payload,
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if proc.returncode != 0:
                err_detail = proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}"
                logger.error("Signal delivery failed via OpenClaw: %s", err_detail)
                return NotificationResult(
                    channel="signal",
                    success=False,
                    message=f"Failed sending chunk {idx}/{len(chunks)}: {err_detail}",
                    error=err_detail,
                )
            sent_count += 1
        except subprocess.TimeoutExpired:
            err_msg = f"Timed out after {timeout}s while sending Signal message to {clean_recipient}"
            logger.error(err_msg)
            return NotificationResult(
                channel="signal",
                success=False,
                message=err_msg,
                error="timeout",
            )
        except Exception as e:
            err_msg = f"Unexpected error executing openclaw: {e}"
            logger.error(err_msg)
            return NotificationResult(
                channel="signal",
                success=False,
                message=err_msg,
                error=str(e),
            )

    return NotificationResult(
        channel="signal",
        success=True,
        message=f"Delivered {sent_count} chunk(s) ({len(message)} chars) to {clean_recipient}",
    )


def send_macos_notification(
    title: str,
    message: str,
    *,
    subtitle: str | None = None,
    dry_run: bool = False,
    timeout: float = 10.0,
) -> NotificationResult:
    """Display a native macOS banner notification via osascript AppleScript."""
    if dry_run:
        return NotificationResult(
            channel="macos",
            success=True,
            message=f"[dry-run] Would display macOS banner: '{title}' - '{message}'",
        )

    # Sanitize strings for AppleScript double-quoted string
    def _escape(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")

    clean_title = _escape(title)
    clean_msg = _escape(message[:250])  # macOS notifications truncate after ~250 chars

    script = f'display notification "{clean_msg}" with title "{clean_title}"'
    if subtitle:
        script += f' subtitle "{_escape(subtitle[:100])}"'

    cmd = ["osascript", "-e", script]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            err = proc.stderr.strip() or "osascript exited non-zero"
            return NotificationResult(channel="macos", success=False, message=err, error=err)
        return NotificationResult(
            channel="macos",
            success=True,
            message=f"Displayed macOS notification: '{clean_title}'",
        )
    except Exception as e:
        logger.error("Failed to trigger macOS notification: %s", e)
        return NotificationResult(channel="macos", success=False, message=str(e), error=str(e))


def dispatch_digest_notifications(
    record: DigestRecord,
    config_obj: DigestConfig | None = None,
    *,
    dry_run: bool = False,
    force_channel: str | None = None,
) -> list[NotificationResult]:
    """Dispatch notifications across configured channels (Signal primary with macOS fallback)."""
    cfg = config_obj or DigestConfig.from_env_or_config()
    results: list[NotificationResult] = []

    # If force_channel is specified (e.g. CLI testing)
    if force_channel == "macos":
        res = send_macos_notification(
            title=record.title,
            message=f"Digest ready at: {record.filepath or 'in-memory'}",
            subtitle=record.date,
            dry_run=dry_run,
        )
        results.append(res)
        record.notifications.extend(results)
        return results

    if force_channel == "signal":
        payload = (
            record.content_markdown
            if cfg.signal_send_full
            else f"🌅 {record.title}\n\nDigest archived at: {record.filepath or 'in-memory'}"
        )
        res = send_signal_message(
            recipient=cfg.signal_recipient or "",
            message=payload,
            dry_run=dry_run,
        )
        results.append(res)
        record.notifications.extend(results)
        return results

    # Normal routing
    signal_succeeded = False

    if cfg.signal_enabled:
        if cfg.signal_recipient:
            payload = (
                record.content_markdown
                if cfg.signal_send_full
                else f"🌅 {record.title}\n\nDigest archived at: {record.filepath or 'in-memory'}"
            )
            sig_res = send_signal_message(
                recipient=cfg.signal_recipient,
                message=payload,
                dry_run=dry_run,
            )
            results.append(sig_res)
            signal_succeeded = sig_res.success
        else:
            results.append(
                NotificationResult(
                    channel="signal",
                    success=False,
                    message=(
                        "Signal enabled but no recipient configured "
                        "(set digest.signal.recipient in config.yml or RIVA_DIGEST_SIGNAL_RECIPIENT)"
                    ),
                    error="missing_recipient",
                )
            )

    # Fallback to macOS notification if Signal was not successful or unconfigured, and fallback is enabled
    if cfg.macos_fallback:
        if not signal_succeeded:
            macos_msg = (
                f"Digest archived at: {record.filepath}"
                if record.filepath
                else "Digest generated (Signal not delivered)"
            )
            mac_res = send_macos_notification(
                title=record.title,
                message=macos_msg,
                subtitle="Riva Daily Digest",
                dry_run=dry_run,
            )
            results.append(mac_res)

    record.notifications.extend(results)
    return results
