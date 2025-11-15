#!/usr/bin/env python3
"""
PDF Password Removal and Attachment Extraction Script

This script removes passwords from encrypted PDF files and extracts any embedded
PDF attachments. It can process a single PDF file or recursively process all PDF
files in a directory. Passwords are read from a password file (one password per line).

Usage:
    python removepassword.py <file_or_dir> [--passwords <path>] [--consume <path>]

Environment Variables:
    - DOCUMENT_WORKING_PATH: Path to a PDF file or directory (takes precedence over arguments)
    - TASK_ID: Optional task identifier for logging purposes

Dependencies:
    - pikepdf: For PDF manipulation and encryption handling
"""

import argparse
import os
from pathlib import Path

import pikepdf


def parse_arguments() -> argparse.Namespace:
    """
    Parse and return command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Remove passwords from PDF files and extract attachments"
    )
    parser.add_argument(
        "file_or_dir",
        nargs="?",
        help="PDF file or directory containing PDF files to process",
    )

    default_pw_file = Path("/usr/src/paperless/scripts/passwords.txt")
    fallback_pw_file = Path("/run/secrets/passwords")
    if not default_pw_file.is_file() and fallback_pw_file.is_file():
        default_pw_file = fallback_pw_file

    parser.add_argument(
        "--passwords",
        type=Path,
        default=default_pw_file,
        help="Path to password file (default: /usr/src/paperless/scripts/passwords.txt or /run/secrets/passwords as fallback)",
    )
    parser.add_argument(
        "--consume",
        type=Path,
        default=Path("/usr/src/paperless/consume/"),
        help="Path to consume directory for extracted attachments (default: /usr/src/paperless/consume/)",
    )
    return parser.parse_args()


def is_pdf(file_path: Path) -> bool:
    """
    Check if a file is a PDF based on its file extension.
    """
    return file_path.suffix.lower() == ".pdf"


def is_pdf_encrypted(file_path: Path) -> bool:
    """
    Check if a PDF file is encrypted.
    """
    try:
        with pikepdf.open(file_path) as pdf:
            return pdf.is_encrypted
    except Exception:
        return True


def pdf_has_attachments(file_path: Path) -> bool:
    """
    Check if a PDF file contains any attachments.
    """
    try:
        with pikepdf.open(file_path) as pdf:
            return len(pdf.attachments) > 0
    except Exception:
        return False


def unlock_pdf(file_path: Path, passwords: list[str]):
    """
    Attempt to decrypt a PDF file using a list of passwords.

    Tries each password in the provided list until one successfully decrypts the PDF.
    The decrypted file is saved back to the original location with deterministic ID.
    """
    success = False
    for password in passwords:
        try:
            with pikepdf.open(
                file_path, password=password, allow_overwriting_input=True
            ) as pdf:
                print(f"Document {file_path} was decrypted succesfully")
                pdf.save(file_path, deterministic_id=True)
            success = True
            break
        except pikepdf.PasswordError:
            continue
    if not success:
        print(f"Failed to decrypt {file_path} with provided passwords")


def extract_pdf_attachments(file_path: Path, consume_path: Path):
    """
    Extract all PDF attachments from a PDF file and save them to the consume directory.

    Iterates through all attachments in the PDF file. Only PDF attachments are extracted
    and saved; non-PDF files are skipped with a message.
    """
    with pikepdf.open(file_path) as pdf:
        ats = pdf.attachments
        for atm in ats:
            spec = ats.get(atm)
            if spec is None:
                print(f"Attachment {atm} could not be retrieved, skipping")
                continue
            trg_filename = Path(spec.filename)
            if is_pdf(trg_filename):
                trg_file_path = consume_path / trg_filename
                try:
                    with trg_file_path.open("wb") as wb:
                        wb.write(spec.obj["/EF"]["/F"].read_bytes())
                    print(f"Attachment {trg_file_path} saved")
                except Exception as e:
                    print(f"Error while writing attachment {trg_file_path}: {e}")
                    continue
            else:
                print(
                    f"Attachment {trg_filename} skipped, because it is not a PDF file"
                )


def process_pdf_file(file_path: Path, passwords: list[str], consume_path: Path):
    """
    Process a single PDF file: decrypt if encrypted and extract attachments.

    This is the main processing function that handles a single PDF. It checks if the file
    is a valid PDF, attempts decryption if encrypted, and extracts any PDF attachments.
    """
    if not is_pdf(file_path):
        print(f"File {file_path} not a PDF file")
        return

    if is_pdf_encrypted(file_path):
        print(f"Document {file_path} is encrypted. Proceeding with decryption")
        unlock_pdf(file_path, passwords)
    else:
        print(f"Document {file_path} is not encrypted. Proceeding without decryption")

    if pdf_has_attachments(file_path):
        print(
            f"Document {file_path} contains attachments. Proceeding with extracting the attachments"
        )
        extract_pdf_attachments(file_path, consume_path)
    else:
        print(f"Document {file_path} has no attachments. Proceeding without decryption")


def get_passwords(file: Path) -> list[str]:
    """
    Read passwords from a text file.
    """
    passwords = (p.strip() for p in file.read_text().splitlines())
    passwords = [p for p in passwords if len(p) > 0]
    print(f"Trying {len(passwords)} from {password_file_path}")
    return passwords


# Variable definition
# You may want to adjust the paths to your needs
args = parse_arguments()

src_file_path = None
src = os.environ.get("DOCUMENT_WORKING_PATH")
if src:
    src_file_path = Path(src)
elif args.file_or_dir:
    src_file_path = Path(args.file_or_dir)

password_file_path = args.passwords
paperless_consume_path = args.consume

task_id = os.environ.get("TASK_ID")
if task_id is not None:
    print(f"Kicking off pre-consumption script for task {task_id}")

if src_file_path is None:
    print("No file or directory path provided.")
    exit(1)
passwords = get_passwords(password_file_path)
if src_file_path.is_file():
    process_pdf_file(src_file_path, passwords, paperless_consume_path)
elif src_file_path.is_dir():
    print(f"Processing directory: {src_file_path}")
    for pdf_file in src_file_path.glob("*.pdf"):
        print(f"\nProcessing: {pdf_file}")
        process_pdf_file(pdf_file, passwords, paperless_consume_path)
else:
    print(f"Path {src_file_path} is neither a file nor a directory")
    exit(1)
