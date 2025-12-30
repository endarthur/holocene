"""Email Handler Plugin - Laney's email interface.

This plugin:
- Polls IMAP for new emails to laney@gentropic.org
- Processes incoming emails:
  - URLs → archives them to the collection
  - Questions → sends to Laney, replies with response
  - Forwarded articles → extracts content and archives
- Sends responses via SMTP
- Runs on rei (server)
"""

import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders
from email.header import decode_header
import mimetypes
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Union
from html import unescape

from holocene.core import Plugin


class EmailHandlerPlugin(Plugin):
    """Handles email communication for Laney."""

    def get_metadata(self):
        return {
            "name": "email_handler",
            "version": "1.0.0",
            "description": "Email interface for Laney - receive questions, archive links",
            "runs_on": ["rei"],
            "requires": []
        }

    def on_load(self):
        """Initialize the plugin."""
        self.logger.info("EmailHandler plugin loading...")

        # Get email config
        email_config = getattr(self.core.config, 'email', None)

        if not email_config or not email_config.enabled:
            self.logger.info("Email not enabled in config")
            self._email_configured = False
            return

        self.email_config = email_config
        self._email_configured = True
        self.logger.info(f"Configured for {email_config.address}")

        # Stats
        self.stats = {
            "emails_processed": 0,
            "emails_replied": 0,
            "links_archived": 0,
            "errors": 0,
            "last_check": None
        }

        # Background thread
        self._check_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Track processed email IDs to avoid reprocessing
        self._processed_ids: set = set()

    def on_enable(self):
        """Enable the plugin and start email checking."""
        if not getattr(self, '_email_configured', False):
            self.logger.warning("Email handler not enabled (missing config)")
            return

        self.logger.info(f"Starting email checker for {self.email_config.address}")

        # Start background email checker
        self._start_email_checker()

    def on_disable(self):
        """Stop the email checker."""
        self._stop_email_checker()
        self.logger.info(f"EmailHandler disabled - Stats: {self.stats}")

    def _start_email_checker(self):
        """Start background thread for checking emails."""
        self._stop_event.clear()
        self._check_thread = threading.Thread(
            target=self._email_check_loop,
            name="email-checker",
            daemon=True
        )
        self._check_thread.start()
        self.logger.info("Email checker thread started")

    def _stop_email_checker(self):
        """Stop the background thread."""
        if self._check_thread:
            self._stop_event.set()
            self._check_thread.join(timeout=10)
            self._check_thread = None

    def _email_check_loop(self):
        """Main loop for checking emails."""
        interval = self.email_config.check_interval_seconds

        while not self._stop_event.is_set():
            try:
                self._check_emails()
            except Exception as e:
                self.logger.error(f"Error checking emails: {e}")
                self.stats["errors"] += 1

            # Wait for interval or stop event
            self._stop_event.wait(interval)

    def _check_emails(self):
        """Check IMAP for new emails and process them."""
        self.stats["last_check"] = datetime.now().isoformat()
        self.logger.debug("Checking for new emails...")

        try:
            # Connect to IMAP
            mail = imaplib.IMAP4_SSL(
                self.email_config.imap_server,
                self.email_config.imap_port
            )
            mail.login(self.email_config.username, self.email_config.password)
            mail.select('INBOX')

            # Search for unread emails
            status, messages = mail.search(None, 'UNSEEN')
            if status != 'OK':
                self.logger.warning("Failed to search emails")
                mail.logout()
                return

            email_ids = messages[0].split()
            if not email_ids:
                self.logger.debug("No new emails")
                mail.logout()
                return

            self.logger.info(f"Found {len(email_ids)} new email(s)")

            for email_id in email_ids:
                try:
                    self._process_email(mail, email_id)
                except Exception as e:
                    self.logger.error(f"Error processing email {email_id}: {e}")
                    self.stats["errors"] += 1

            mail.logout()

        except imaplib.IMAP4.error as e:
            self.logger.error(f"IMAP error: {e}")
            self.stats["errors"] += 1
        except Exception as e:
            self.logger.error(f"Error checking emails: {e}")
            self.stats["errors"] += 1

    def _process_email(self, mail: imaplib.IMAP4_SSL, email_id: bytes):
        """Process a single email."""
        # Fetch the email
        status, msg_data = mail.fetch(email_id, '(RFC822)')
        if status != 'OK':
            return

        # Parse email
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        # Extract headers
        subject = self._decode_header(msg['Subject'])
        from_addr = self._extract_email_address(msg['From'])
        to_addr = msg['To']
        date = msg['Date']
        message_id = msg['Message-ID']

        self.logger.info(f"Processing email from {from_addr}: {subject}")

        # Check if sender is allowed
        if self.email_config.allowed_senders:
            if not self._is_sender_allowed(from_addr):
                self.logger.info(f"Ignoring email from non-allowed sender: {from_addr}")
                return

        # Extract body
        body = self._extract_body(msg)

        # Determine what to do with the email
        urls = self._extract_urls(body)

        # Check if it's just URLs (archive them)
        body_without_urls = re.sub(r'https?://[^\s]+', '', body).strip()
        is_urls_only = len(body_without_urls) < 50 and urls

        if is_urls_only:
            # Archive the URLs
            self.logger.info(f"URL-only email with {len(urls)} URLs - archiving")
            self._handle_url_email(from_addr, subject, urls, message_id, msg)
        else:
            # Send to Laney for a response
            self.logger.info("Question email - sending to Laney...")
            self._handle_question_email(from_addr, subject, body, message_id, msg)

        self.stats["emails_processed"] += 1

    def _handle_url_email(self, from_addr: str, subject: str, urls: List[str],
                          message_id: str, original_msg):
        """Handle an email containing URLs to archive."""
        self.logger.info(f"Archiving {len(urls)} URLs from email")

        archived = []
        failed = []

        for url in urls:
            try:
                # Add link to database
                result = self._add_link(url, source=f"email:{from_addr}")
                if result:
                    archived.append(url)
                    self.stats["links_archived"] += 1
                else:
                    failed.append(url)
            except Exception as e:
                self.logger.error(f"Failed to archive {url}: {e}")
                failed.append(url)

        # Send confirmation reply
        reply_body = f"Thanks for the links! Here's what I did:\n\n"

        if archived:
            reply_body += "**Archived:**\n"
            for url in archived:
                reply_body += f"- {url}\n"

        if failed:
            reply_body += "\n**Failed:**\n"
            for url in failed:
                reply_body += f"- {url}\n"

        reply_body += f"\n---\n*Laney - laney@gentropic.org*"

        self._send_reply(from_addr, f"Re: {subject}", reply_body, message_id)

    def _handle_question_email(self, from_addr: str, subject: str, body: str,
                               message_id: str, original_msg):
        """Handle an email with a question for Laney."""
        self.logger.info(f"Processing question from {from_addr}")

        try:
            # Get Laney's response
            response = self._ask_laney(body, context=f"Email from {from_addr}, Subject: {subject}")

            # Send reply
            reply_body = f"{response}\n\n---\n*Laney - laney@gentropic.org*"
            self._send_reply(from_addr, f"Re: {subject}", reply_body, message_id)

            self.stats["emails_replied"] += 1

        except Exception as e:
            self.logger.error(f"Failed to get Laney response: {e}")
            # Send error reply
            error_body = (
                f"I encountered an error processing your message:\n\n"
                f"`{str(e)[:200]}`\n\n"
                f"Please try again or contact Arthur.\n\n"
                f"---\n*Laney - laney@gentropic.org*"
            )
            self._send_reply(from_addr, f"Re: {subject}", error_body, message_id)

    def _ask_laney(self, query: str, context: str = "") -> str:
        """Send a query to Laney and get response."""
        from ..llm.nanogpt import NanoGPTClient
        from ..llm.laney_tools import LANEY_TOOLS, LaneyToolHandler
        from ..cli.laney_commands import LANEY_SYSTEM_PROMPT

        config = self.core.config
        client = NanoGPTClient(config.llm.api_key, config.llm.base_url)
        tool_handler = LaneyToolHandler(
            db_path=config.db_path,
            brave_api_key=getattr(config.integrations, 'brave_api_key', None),
        )

        # Add email context to system prompt
        system_prompt = LANEY_SYSTEM_PROMPT + f"\n\nContext: {context}\n\nRespond concisely - this is an email reply."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]

        response = client.run_with_tools(
            messages=messages,
            tools=LANEY_TOOLS,
            tool_handlers=tool_handler.handlers,
            model=config.llm.primary,
            temperature=0.3,
            max_iterations=10,
            timeout=300
        )

        tool_handler.close()
        return response

    def _add_link(self, url: str, source: str = "email") -> bool:
        """Add a link to the database."""
        try:
            db = self.core.db
            now = datetime.now().isoformat()

            # Check if link already exists
            existing = db.conn.execute(
                "SELECT id FROM links WHERE url = ?", (url,)
            ).fetchone()

            if existing:
                self.logger.info(f"Link already exists: {url}")
                return True

            # Insert new link
            db.conn.execute("""
                INSERT INTO links (url, source, created_at, trust_tier)
                VALUES (?, ?, ?, 'recent')
            """, (url, source, now))
            db.conn.commit()

            self.logger.info(f"Added link: {url}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to add link: {e}")
            return False

    def _send_reply(self, to_addr: str, subject: str, body: str,
                    in_reply_to: str = None,
                    attachments: Optional[List[Tuple[str, bytes, str]]] = None):
        """Send an email reply via SMTP.

        Args:
            to_addr: Recipient email address
            subject: Email subject
            body: Email body (markdown-ish text)
            in_reply_to: Message-ID for threading
            attachments: List of (filename, content_bytes, mime_type) tuples
        """
        try:
            # Use mixed for attachments, alternative for text/html only
            if attachments:
                msg = MIMEMultipart('mixed')
                # Create alternative part for text/html body
                alt_part = MIMEMultipart('alternative')
                text_part = MIMEText(body, 'plain', 'utf-8')
                alt_part.attach(text_part)
                html_body = self._markdown_to_html(body)
                html_part = MIMEText(html_body, 'html', 'utf-8')
                alt_part.attach(html_part)
                msg.attach(alt_part)
            else:
                msg = MIMEMultipart('alternative')
                text_part = MIMEText(body, 'plain', 'utf-8')
                msg.attach(text_part)
                html_body = self._markdown_to_html(body)
                html_part = MIMEText(html_body, 'html', 'utf-8')
                msg.attach(html_part)

            msg['From'] = self.email_config.address
            msg['To'] = to_addr
            msg['Subject'] = subject

            if in_reply_to:
                msg['In-Reply-To'] = in_reply_to
                msg['References'] = in_reply_to

            # Add attachments
            if attachments:
                for filename, content, mime_type in attachments:
                    maintype, subtype = mime_type.split('/', 1)

                    if maintype == 'image':
                        part = MIMEImage(content, _subtype=subtype)
                    else:
                        part = MIMEBase(maintype, subtype)
                        part.set_payload(content)
                        encoders.encode_base64(part)

                    part.add_header('Content-Disposition', 'attachment', filename=filename)
                    msg.attach(part)
                    self.logger.info(f"Attached: {filename} ({mime_type})")

            # Send via SMTP
            with smtplib.SMTP(self.email_config.smtp_server, self.email_config.smtp_port) as server:
                server.starttls()
                server.login(self.email_config.username, self.email_config.password)
                server.send_message(msg)

            attachment_info = f" with {len(attachments)} attachment(s)" if attachments else ""
            self.logger.info(f"Sent reply to {to_addr}: {subject}{attachment_info}")

        except Exception as e:
            self.logger.error(f"Failed to send email: {e}")
            raise

    def _attach_file(self, filepath: Union[str, Path]) -> Optional[Tuple[str, bytes, str]]:
        """Read a file and prepare it for attachment.

        Args:
            filepath: Path to file

        Returns:
            Tuple of (filename, content, mime_type) or None if failed
        """
        try:
            path = Path(filepath)
            if not path.exists():
                self.logger.error(f"Attachment file not found: {filepath}")
                return None

            # Guess mime type
            mime_type, _ = mimetypes.guess_type(str(path))
            if mime_type is None:
                mime_type = 'application/octet-stream'

            content = path.read_bytes()
            return (path.name, content, mime_type)

        except Exception as e:
            self.logger.error(f"Failed to read attachment {filepath}: {e}")
            return None

    def _decode_header(self, header: str) -> str:
        """Decode email header value."""
        if not header:
            return ""

        decoded_parts = decode_header(header)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(encoding or 'utf-8', errors='replace'))
            else:
                result.append(part)
        return ''.join(result)

    def _extract_email_address(self, from_header: str) -> str:
        """Extract email address from From header."""
        if not from_header:
            return ""

        # Try to extract just the email address
        match = re.search(r'<([^>]+)>', from_header)
        if match:
            return match.group(1)

        # Maybe it's just an email address
        match = re.search(r'[\w.-]+@[\w.-]+', from_header)
        if match:
            return match.group(0)

        return from_header

    def _is_sender_allowed(self, from_addr: str) -> bool:
        """Check if sender is in allowed list.

        Supports:
        - Exact email matches: endarthur@gmail.com
        - Domain wildcards: @gentropic.org (matches any @gentropic.org address)
        """
        from_lower = from_addr.lower()

        for allowed in self.email_config.allowed_senders:
            allowed_lower = allowed.lower()

            if allowed_lower.startswith('@'):
                # Domain wildcard - check if sender's domain matches
                if from_lower.endswith(allowed_lower):
                    return True
            else:
                # Exact email match
                if from_lower == allowed_lower:
                    return True

        return False

    def _extract_body(self, msg) -> str:
        """Extract text body from email message."""
        body = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                # Skip attachments
                if "attachment" in content_disposition:
                    continue

                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        body = payload.decode(charset, errors='replace')
                        break
                elif content_type == "text/html" and not body:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        html = payload.decode(charset, errors='replace')
                        body = self._html_to_text(html)
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or 'utf-8'
                body = payload.decode(charset, errors='replace')

        return body.strip()

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text (basic)."""
        # Remove script and style elements
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # Replace common elements
        html = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
        html = re.sub(r'<p[^>]*>', '\n\n', html, flags=re.IGNORECASE)
        html = re.sub(r'</p>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'<div[^>]*>', '\n', html, flags=re.IGNORECASE)

        # Remove all remaining tags
        html = re.sub(r'<[^>]+>', '', html)

        # Decode HTML entities
        html = unescape(html)

        # Clean up whitespace
        html = re.sub(r'\n\s*\n', '\n\n', html)
        return html.strip()

    def _markdown_to_html(self, text: str) -> str:
        """Convert basic markdown to HTML."""
        html = text

        # Bold
        html = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'__([^_]+)__', r'<strong>\1</strong>', html)

        # Italic
        html = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', html)
        html = re.sub(r'_([^_]+)_', r'<em>\1</em>', html)

        # Code
        html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)

        # Links
        html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)

        # Line breaks
        html = html.replace('\n', '<br>\n')

        return f"<html><body>{html}</body></html>"

    def _extract_urls(self, text: str) -> List[str]:
        """Extract URLs from text."""
        url_pattern = r'https?://[^\s<>"\')\]]+[^\s<>"\')\].,;:!?]'
        urls = re.findall(url_pattern, text)
        return list(set(urls))  # Deduplicate
