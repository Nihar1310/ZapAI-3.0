"""Email masking utility for GDPR compliance and privacy protection."""

import re
from typing import List, Optional, Union
from enum import Enum


class MaskingStyle(Enum):
    """Different email masking styles."""
    PARTIAL = "partial"  # j••••@ex••••.com
    MINIMAL = "minimal"  # j***@example.com  
    ASTERISK = "asterisk"  # j****@ex****.com
    DOTS = "dots"  # j•••@ex•••.com (default)
    FIRST_LAST = "first_last"  # j••••e@ex••••.com


class EmailMasker:
    """Utility class for masking email addresses in various formats."""
    
    def __init__(self, default_style: MaskingStyle = MaskingStyle.DOTS):
        """Initialize with default masking style."""
        self.default_style = default_style
        self._email_regex = re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        )
    
    def mask_email(
        self, 
        email: str, 
        style: Optional[MaskingStyle] = None,
        preserve_domain: bool = True
    ) -> str:
        """
        Mask a single email address.
        
        Args:
            email: The email address to mask
            style: Masking style to use (defaults to instance default)
            preserve_domain: Whether to mask the domain or just the local part
            
        Returns:
            Masked email address
            
        Examples:
            >>> masker = EmailMasker()
            >>> masker.mask_email("john.doe@example.com")
            'j•••••••@ex•••••.com'
            >>> masker.mask_email("admin@company.co.uk", MaskingStyle.MINIMAL, preserve_domain=False)
            'a***@c******.co.uk'
        """
        if not self.is_valid_email(email):
            return email  # Return as-is if not a valid email
        
        style = style or self.default_style
        email = email.lower().strip()
        
        try:
            local, domain = email.split('@', 1)
            
            # Mask local part
            masked_local = self._mask_local_part(local, style)
            
            # Mask domain if requested
            if preserve_domain:
                masked_domain = domain
            else:
                masked_domain = self._mask_domain_part(domain, style)
            
            return f"{masked_local}@{masked_domain}"
            
        except Exception:
            # Fallback for any parsing errors
            return self._basic_mask(email)
    
    def mask_emails(
        self, 
        emails: Union[str, List[str]], 
        style: Optional[MaskingStyle] = None,
        preserve_domain: bool = True
    ) -> Union[str, List[str]]:
        """
        Mask multiple emails or emails within text.
        
        Args:
            emails: Single email, list of emails, or text containing emails
            style: Masking style to use
            preserve_domain: Whether to preserve domain visibility
            
        Returns:
            Masked email(s) in the same format as input
        """
        if isinstance(emails, str):
            if self.is_valid_email(emails):
                # Single email string
                return self.mask_email(emails, style, preserve_domain)
            else:
                # Text containing emails - replace all found emails
                return self._mask_emails_in_text(emails, style, preserve_domain)
        
        elif isinstance(emails, list):
            # List of emails
            return [
                self.mask_email(email, style, preserve_domain) 
                for email in emails
            ]
        
        else:
            return emails  # Return as-is for unsupported types
    
    def _mask_local_part(self, local: str, style: MaskingStyle) -> str:
        """Mask the local part of an email (before @)."""
        if len(local) <= 1:
            return local  # Don't mask very short local parts
        
        if style == MaskingStyle.MINIMAL:
            # Show first character, mask rest with asterisks
            return local[0] + '*' * min(3, len(local) - 1)
        
        elif style == MaskingStyle.ASTERISK:
            # Show first char, mask middle with asterisks, show last if long enough
            if len(local) <= 3:
                return local[0] + '*' * (len(local) - 1)
            else:
                middle_count = len(local) - 2
                return local[0] + '*' * min(4, middle_count) + local[-1]
        
        elif style == MaskingStyle.FIRST_LAST:
            # Show first and last character, mask middle with dots
            if len(local) <= 3:
                return local[0] + '•' * (len(local) - 1)
            else:
                middle_count = len(local) - 2
                return local[0] + '•' * middle_count + local[-1]
        
        elif style == MaskingStyle.PARTIAL:
            # Show first char, mask 60% of remaining with dots
            if len(local) <= 2:
                return local[0] + '•' * (len(local) - 1)
            else:
                visible_end = max(1, int(len(local) * 0.3))
                masked_count = len(local) - 1 - visible_end
                return local[0] + '•' * masked_count + local[-visible_end:]
        
        else:  # MaskingStyle.DOTS (default)
            # Show first character, mask rest with dots
            return local[0] + '•' * (len(local) - 1)
    
    def _mask_domain_part(self, domain: str, style: MaskingStyle) -> str:
        """Mask the domain part of an email (after @)."""
        if '.' not in domain:
            return domain  # Don't mask domains without TLD
        
        parts = domain.split('.')
        if len(parts) < 2:
            return domain
        
        # Always preserve TLD (.com, .org, etc.)
        tld = parts[-1]
        domain_name = '.'.join(parts[:-1])
        
        if len(domain_name) <= 2:
            return domain  # Don't mask very short domains
        
        # Apply same masking logic as local part
        masked_name = self._mask_local_part(domain_name.replace('.', ''), style)
        
        # Restore dots in domain structure if needed
        if '.' in domain_name:
            # For multi-level domains, mask each part
            name_parts = domain_name.split('.')
            masked_parts = []
            for part in name_parts:
                if len(part) > 1:
                    masked_parts.append(self._mask_local_part(part, style))
                else:
                    masked_parts.append(part)
            masked_name = '.'.join(masked_parts)
        
        return f"{masked_name}.{tld}"
    
    def _mask_emails_in_text(
        self, 
        text: str, 
        style: Optional[MaskingStyle] = None,
        preserve_domain: bool = True
    ) -> str:
        """Replace all email addresses in text with masked versions."""
        def mask_match(match):
            email = match.group(0)
            return self.mask_email(email, style, preserve_domain)
        
        return self._email_regex.sub(mask_match, text)
    
    def _basic_mask(self, email: str) -> str:
        """Basic fallback masking for malformed emails."""
        if '@' in email:
            local, domain = email.split('@', 1)
            if len(local) > 1:
                return local[0] + '•' * (len(local) - 1) + '@' + domain
        return email[:2] + '•' * max(0, len(email) - 4) + email[-2:] if len(email) > 4 else email
    
    def is_valid_email(self, email: str) -> bool:
        """Check if a string is a valid email format."""
        if not isinstance(email, str) or '@' not in email:
            return False
        return bool(self._email_regex.match(email.strip()))
    
    def unmask_preview(self, masked_email: str) -> str:
        """
        Generate hint about the original email format (for debugging/preview).
        This does NOT unmask the email, just provides structure info.
        """
        if '@' not in masked_email:
            return "Invalid email format"
        
        local, domain = masked_email.split('@', 1)
        
        # Count visible vs masked characters
        visible_count = len([c for c in local if c not in '•*'])
        masked_count = len([c for c in local if c in '•*'])
        
        return f"Format: {visible_count} visible + {masked_count} masked characters @ {domain}"


# Convenience functions for direct usage
def mask_email(
    email: str, 
    style: MaskingStyle = MaskingStyle.DOTS,
    preserve_domain: bool = True
) -> str:
    """
    Quick function to mask a single email.
    
    Args:
        email: Email address to mask
        style: Masking style (default: DOTS)
        preserve_domain: Whether to keep domain visible
        
    Returns:
        Masked email address
    """
    masker = EmailMasker(style)
    return masker.mask_email(email, style, preserve_domain)


def mask_emails_in_list(
    emails: List[str], 
    style: MaskingStyle = MaskingStyle.DOTS,
    preserve_domain: bool = True
) -> List[str]:
    """
    Quick function to mask a list of emails.
    
    Args:
        emails: List of email addresses
        style: Masking style (default: DOTS)
        preserve_domain: Whether to keep domains visible
        
    Returns:
        List of masked email addresses
    """
    masker = EmailMasker(style)
    result = masker.mask_emails(emails, style, preserve_domain)
    # Ensure we return a list since input is guaranteed to be a list
    return result if isinstance(result, list) else [result]


def mask_emails_in_text(
    text: str, 
    style: MaskingStyle = MaskingStyle.DOTS,
    preserve_domain: bool = True
) -> str:
    """
    Quick function to mask all emails found in text.
    
    Args:
        text: Text containing email addresses
        style: Masking style (default: DOTS)
        preserve_domain: Whether to keep domains visible
        
    Returns:
        Text with all emails masked
    """
    masker = EmailMasker(style)
    result = masker.mask_emails(text, style, preserve_domain)
    # Ensure we return a string since input is guaranteed to be a string
    return result if isinstance(result, str) else str(result)


# For integration with ContactData model
def mask_contact_emails(
    contact_data_emails: List[str], 
    style: MaskingStyle = MaskingStyle.DOTS
) -> List[str]:
    """
    Mask emails specifically for ContactData model integration.
    This preserves domains for better user experience in previews.
    
    Args:
        contact_data_emails: List of emails from ContactData.emails field
        style: Masking style for GDPR compliance
        
    Returns:
        List of masked emails suitable for preview display
    """
    if not contact_data_emails:
        return []
    
    return mask_emails_in_list(
        contact_data_emails, 
        style=style, 
        preserve_domain=True  # Always preserve domains in contact previews
    )
