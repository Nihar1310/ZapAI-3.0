"""Utility functions for ZapAI application."""

from .mask import (
    EmailMasker,
    MaskingStyle,
    mask_email,
    mask_emails_in_list,
    mask_emails_in_text,
    mask_contact_emails
)

__all__ = [
    "EmailMasker",
    "MaskingStyle", 
    "mask_email",
    "mask_emails_in_list",
    "mask_emails_in_text",
    "mask_contact_emails"
]
