#!/usr/bin/env python3
import argparse
import socket
import ssl
import threading
import os
import subprocess
import shutil

HOST = '127.0.0.1'
PORT = 8443
CERT_FILE = 'server.crt'
KEY_FILE = 'server.key'


def generate_self_signed(certfile=CERT_FILE, keyfile=KEY_FILE):
    """Try to generate a self-signed certificate using openssl if available."""
    if shutil.which('openssl') is None:
        return False, 'openssl not found'
    cmd = [
        'openssl', 'req', '-x509', '-nodes', '-days', '365', '-newkey', 'rsa:2048',
        '-keyout', keyfile, '-out', certfile,
        '-subj', '/CN=localhost'
    ]
    try:
        subprocess.check_call(cmd)
        return True, 'generated via openssl'
    except Exception as e:
        return False, str(e)


def handle_secure_connection(conn, addr):
    print(f"Secure connection established from {addr}")
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            try:
                message = data.decode(errors='replace')
            except Exception:
                message = '<binary data>'
            print(f"Server received: {message}")
            response = "Server acknowledges receipt of your secured message."
            conn.sendall(response.encode())
    except Exception as e:
        print(f"Error with client {addr}: {e}")
    finally:
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        conn.close()
        print(f"Connection closed for {addr}")


def run_server(use_ssl=True):
    if use_ssl:
        if not (os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE)):
            ok, msg = generate_self_signed()
            if not ok:
                print(f"Cert/key not found and auto-generation failed: {msg}")
                print("Falling back to plain TCP server for testing. (Not secure)")
                use_ssl = False
            else:
                print(f"Created self-signed cert/key ({msg}).")

    if use_ssl:
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)

    bindsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    bindsocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    bindsocket.bind((HOST, PORT))
    bindsocket.listen(5)
    print(f"Server listening on {HOST}:{PORT} (ssl={'yes' if use_ssl else 'no'})")

    try:
        while True:
            newsock, addr = bindsocket.accept()
            if use_ssl:
                try:
                    ssock = context.wrap_socket(newsock, server_side=True)
                except ssl.SSLError as e:
                    print(f"SSL handshake failed: {e}")
                    newsock.close()
                    continue
                t = threading.Thread(target=handle_secure_connection, args=(ssock, addr), daemon=True)
            else:
                t = threading.Thread(target=handle_secure_connection, args=(newsock, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print('\nShutting down server...')
    finally:
        bindsocket.close()


def run_client(use_ssl=True, insecure=False, message=None):
    raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        raw.connect((HOST, PORT))
    except Exception as e:
        print(f"Connection failed: {e}")
        raw.close()
        return

    if use_ssl:
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        if insecure:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        try:
            conn = context.wrap_socket(raw, server_hostname=HOST if not insecure else None)
            print(f"Secure tunnel established with {HOST}:{PORT}")
        except Exception as e:
            print(f"SSL handshake failed: {e}")
            raw.close()
            return
    else:
        conn = raw
        print(f"Plain TCP connection established with {HOST}:{PORT}")

    try:
        msg = message or "Encrypted data payload from the custom client."
        conn.sendall(msg.encode())
        print(f"Sent: {msg}")
        resp = conn.recv(4096)
        print(f"Received: {resp.decode(errors='replace')}")
    except Exception as e:
        print(f"Communication error: {e}")
    finally:
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        conn.close()
        print("Connection closed.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['server','client'], help='Run as server or client')
    parser.add_argument('--insecure', action='store_true', help='Client: do not verify server cert (for self-signed)')
    parser.add_argument('--plain', action='store_true', help='Force plain TCP (no TLS)')
    parser.add_argument('--message', help='Message to send from client')
    args = parser.parse_args()

    if args.mode == 'server':
        run_server(use_ssl=not args.plain)
    else:
        run_client(use_ssl=not args.plain, insecure=args.insecure, message=args.message)
