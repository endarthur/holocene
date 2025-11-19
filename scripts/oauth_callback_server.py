#!/usr/bin/env python3
"""
Simple HTTPS callback server for OAuth 2.0 flow.

Runs a temporary HTTPS server on https://127.0.0.1:8080/auth/callback
to receive the OAuth authorization code.

This handles the Mercado Livre HTTPS requirement for redirect URIs.
"""

import http.server
import ssl
import urllib.parse
import sys
from pathlib import Path

# HTML template for success page
SUCCESS_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Holocene - Authorization Successful</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .container {
            background: white;
            padding: 3rem;
            border-radius: 1rem;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
            max-width: 500px;
        }
        h1 {
            color: #2d3748;
            margin: 0 0 1rem 0;
        }
        .checkmark {
            font-size: 4rem;
            color: #48bb78;
            margin-bottom: 1rem;
        }
        .code {
            background: #f7fafc;
            padding: 1rem;
            border-radius: 0.5rem;
            font-family: monospace;
            color: #2d3748;
            margin: 1rem 0;
            word-break: break-all;
        }
        p {
            color: #718096;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="checkmark">✓</div>
        <h1>Authorization Successful!</h1>
        <p>Authorization code received:</p>
        <div class="code">{code}</div>
        <p>You can close this window and return to the terminal.</p>
    </div>
</body>
</html>
"""


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for OAuth callback."""

    authorization_code = None

    def do_GET(self):
        """Handle GET request from OAuth redirect."""
        # Parse the URL
        parsed_path = urllib.parse.urlparse(self.path)

        if parsed_path.path == '/auth/callback':
            # Extract query parameters
            query_params = urllib.parse.parse_qs(parsed_path.query)

            if 'code' in query_params:
                # Got the authorization code!
                code = query_params['code'][0]
                OAuthCallbackHandler.authorization_code = code

                # Send success response
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(SUCCESS_HTML.format(code=code).encode())

                print(f"\n✓ Authorization code received: {code}")
                print("\nYou can close the browser window now.")

            elif 'error' in query_params:
                # OAuth error
                error = query_params['error'][0]
                error_desc = query_params.get('error_description', ['Unknown error'])[0]

                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(f"<h1>Authorization Failed</h1><p>{error}: {error_desc}</p>".encode())

                print(f"\n✗ Authorization failed: {error} - {error_desc}")

            else:
                # No code or error - unexpected
                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"<h1>Invalid Request</h1><p>No authorization code received.</p>")
        else:
            # Wrong path
            self.send_response(404)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"<h1>404 Not Found</h1>")

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass  # Silent unless we get the callback


def generate_self_signed_cert():
    """Generate a self-signed certificate for HTTPS."""
    try:
        import subprocess

        cert_file = Path.home() / ".holocene" / "oauth_cert.pem"
        cert_file.parent.mkdir(parents=True, exist_ok=True)

        if cert_file.exists():
            return str(cert_file)

        # Generate self-signed cert using OpenSSL
        # This requires OpenSSL to be installed
        subprocess.run([
            "openssl", "req", "-new", "-x509", "-keyout", str(cert_file),
            "-out", str(cert_file), "-days", "365", "-nodes",
            "-subj", "/CN=127.0.0.1"
        ], check=True, capture_output=True)

        return str(cert_file)

    except (subprocess.CalledProcessError, FileNotFoundError):
        # OpenSSL not available, use Python's ssl module
        print("⚠ OpenSSL not found. Browser will show security warning (this is normal).")
        return None


def run_callback_server(port=8080, timeout=300):
    """
    Run HTTPS callback server to receive OAuth code.

    Args:
        port: Port to listen on (default 8080)
        timeout: Timeout in seconds (default 5 minutes)

    Returns:
        Authorization code if received, None otherwise
    """
    server_address = ('127.0.0.1', port)
    httpd = http.server.HTTPServer(server_address, OAuthCallbackHandler)

    # Try to set up SSL
    try:
        # Create SSL context with self-signed cert
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        # Try to load/generate certificate
        cert_file = generate_self_signed_cert()
        if cert_file:
            context.load_cert_chain(cert_file)
        else:
            # Use adhoc cert (will cause browser warning)
            import tempfile
            from OpenSSL import crypto

            # Generate key and cert
            k = crypto.PKey()
            k.generate_key(crypto.TYPE_RSA, 2048)

            cert = crypto.X509()
            cert.get_subject().CN = "127.0.0.1"
            cert.set_serial_number(1000)
            cert.gmtime_adj_notBefore(0)
            cert.gmtime_adj_notAfter(365*24*60*60)
            cert.set_issuer(cert.get_subject())
            cert.set_pubkey(k)
            cert.sign(k, 'sha256')

            # Save to temp file
            with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pem') as f:
                f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
                f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))
                temp_cert = f.name

            context.load_cert_chain(temp_cert)

        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

    except Exception as e:
        print(f"⚠ Could not set up HTTPS: {e}")
        print("Falling back to HTTP (may not work with Mercado Livre)")

    print(f"\n✓ OAuth callback server running at https://127.0.0.1:{port}/auth/callback")
    print("⚠ If browser shows security warning, click 'Advanced' → 'Proceed' (this is safe)")
    print(f"\nWaiting for authorization callback (timeout: {timeout}s)...")
    print("Open the authorization URL in your browser now.\n")

    # Set timeout
    httpd.timeout = timeout

    # Wait for one request
    try:
        httpd.handle_request()
    except KeyboardInterrupt:
        print("\n\n✗ Cancelled by user")
        return None

    if OAuthCallbackHandler.authorization_code:
        return OAuthCallbackHandler.authorization_code
    else:
        print(f"\n✗ No authorization code received within {timeout}s")
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="OAuth callback server for Holocene")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds (default: 300)")
    args = parser.parse_args()

    code = run_callback_server(port=args.port, timeout=args.timeout)

    if code:
        print(f"\n✓ Success! Use this code in your CLI:")
        print(f"\n  {code}\n")
        sys.exit(0)
    else:
        print("\n✗ Failed to receive authorization code")
        sys.exit(1)
