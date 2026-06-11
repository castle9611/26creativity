# -*- coding: utf-8 -*-
"""
Input validation utilities for form data and user input.
"""
import re
from datetime import datetime


def validate_username(username):
    """
    Validate username format.

    Args:
        username: Username string.

    Returns:
        Tuple (is_valid, error_message).
    """
    if not username:
        return False, '用户名不能为空'

    if len(username) < 3:
        return False, '用户名长度不能少于3个字符'

    if len(username) > 50:
        return False, '用户名长度不能超过50个字符'

    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, '用户名只能包含字母、数字和下划线'

    return True, ''


def validate_real_name(name):
    """
    Validate real name.

    Args:
        name: Real name string.

    Returns:
        Tuple (is_valid, error_message).
    """
    if not name:
        return True, ''  # Real name is optional

    if len(name) > 50:
        return False, '姓名长度不能超过50个字符'

    return True, ''


def validate_password(password):
    """
    Validate password (basic check, 6+ chars).

    Args:
        password: Password string.

    Returns:
        Tuple (is_valid, error_message).
    """
    if not password:
        return False, '密码不能为空'

    if len(password) < 6:
        return False, '密码长度不能少于6位'

    return True, ''


def validate_password_strength(password, min_length=8, require_uppercase=True,
                              require_lowercase=True, require_digit=True,
                              require_special=False):
    """
    Validate password meets security requirements.

    Args:
        password: Password string.
        min_length: Minimum length.
        require_uppercase: Require uppercase letter.
        require_lowercase: Require lowercase letter.
        require_digit: Require digit.
        require_special: Require special character.

    Returns:
        Tuple (is_valid, error_message).
    """
    if not password:
        return False, '密码不能为空'

    if len(password) < min_length:
        return False, f'密码长度不能少于{min_length}位'

    if require_uppercase and not any(c.isupper() for c in password):
        return False, '密码必须包含大写字母'

    if require_lowercase and not any(c.islower() for c in password):
        return False, '密码必须包含小写字母'

    if require_digit and not any(c.isdigit() for c in password):
        return False, '密码必须包含数字'

    if require_special and not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password):
        return False, '密码必须包含特殊字符'

    return True, ''


def validate_date(date_str, date_format='%Y-%m-%d'):
    """
    Validate date string format.

    Args:
        date_str: Date string.
        date_format: Expected format.

    Returns:
        Tuple (is_valid, error_message).
    """
    if not date_str:
        return True, ''  # Date is optional

    try:
        datetime.strptime(date_str, date_format)
        return True, ''
    except ValueError:
        return False, f'日期格式错误，请使用{date_format}格式'


def validate_required(*fields):
    """
    Validate required fields are not empty.

    Args:
        *fields: Field name and value pairs.

    Returns:
        Tuple (is_valid, missing_fields_list).
    """
    missing = []
    for i in range(0, len(fields), 2):
        field_name = fields[i]
        field_value = fields[i + 1]
        if not field_value or (isinstance(field_value, str) and not field_value.strip()):
            missing.append(field_name)

    if missing:
        return False, missing
    return True, []


def validate_email(email):
    """
    Validate email format.

    Args:
        email: Email string.

    Returns:
        Tuple (is_valid, error_message).
    """
    if not email:
        return True, ''  # Email is optional

    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, '邮箱格式不正确'

    return True, ''


def validate_phone(phone):
    """
    Validate phone number format.

    Args:
        phone: Phone string.

    Returns:
        Tuple (is_valid, error_message).
    """
    if not phone:
        return True, ''  # Phone is optional

    # Chinese phone/mobile pattern
    pattern = r'^1[3-9]\d{9}$|^\d{3,4}-?\d{7,8}$'
    if not re.match(pattern, phone):
        return False, '电话号码格式不正确'

    return True, ''


def validate_file_extension(filename, allowed_extensions):
    """
    Validate file extension.

    Args:
        filename: Original filename.
        allowed_extensions: Set or list of allowed extensions.

    Returns:
        Tuple (is_valid, error_message).
    """
    if not filename:
        return False, '文件名不能为空'

    if '.' not in filename:
        return False, '文件格式不正确'

    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in allowed_extensions:
        return False, f'不支持的文件格式，仅支持: {", ".join(allowed_extensions)}'

    return True, ''


def validate_title(title, min_length=1, max_length=500):
    """
    Validate title field.

    Args:
        title: Title string.
        min_length: Minimum length.
        max_length: Maximum length.

    Returns:
        Tuple (is_valid, error_message).
    """
    if not title:
        return False, '标题不能为空'

    title = title.strip()
    if len(title) < min_length:
        return False, f'标题长度不能少于{min_length}个字符'

    if len(title) > max_length:
        return False, f'标题长度不能超过{max_length}个字符'

    return True, ''


def validate_content(content, max_length=None):
    """
    Validate content field.

    Args:
        content: Content string.
        max_length: Optional maximum length.

    Returns:
        Tuple (is_valid, error_message).
    """
    if not content:
        return True, ''  # Content is optional

    if max_length and len(content) > max_length:
        return False, f'内容长度不能超过{max_length}个字符'

    return True, ''


def validate_department(department, max_length=100):
    """
    Validate department field.

    Args:
        department: Department string.
        max_length: Maximum length.

    Returns:
        Tuple (is_valid, error_message).
    """
    if not department:
        return True, ''  # Department is optional

    if len(department) > max_length:
        return False, f'部门名称不能超过{max_length}个字符'

    return True, ''


def validate_ip_address(ip):
    """
    Validate IP address format.

    Args:
        ip: IP address string.

    Returns:
        Tuple (is_valid, error_message).
    """
    if not ip:
        return True, ''  # IP is optional

    # IPv4 pattern
    ipv4_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    # IPv6 pattern (simplified)
    ipv6_pattern = r'^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$'

    if not (re.match(ipv4_pattern, ip) or re.match(ipv6_pattern, ip)):
        return False, 'IP地址格式不正确'

    # Validate IPv4 octets
    if re.match(ipv4_pattern, ip):
        octets = ip.split('.')
        for octet in octets:
            if int(octet) > 255:
                return False, 'IP地址格式不正确'

    return True, ''


def sanitize_html(html_content, allowed_tags=None):
    """
    Basic HTML sanitization for rich text content.

    Note: For production, consider using the 'bleach' library.

    Args:
        html_content: HTML content string.
        allowed_tags: List of allowed tags. If None, uses default.

    Returns:
        Sanitized HTML string.
    """
    if not html_content:
        return html_content

    # Basic XSS prevention: escape script and event handlers
    dangerous_patterns = [
        (r'<script[^>]*>.*?</script>', ''),
        (r'on\w+\s*=', ''),  # Event handlers
        (r'javascript:', ''),
        (r'<iframe[^>]*>.*?</iframe>', ''),
    ]

    result = html_content
    for pattern, replacement in dangerous_patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE | re.DOTALL)

    return result


def validate_pagination_params(page, per_page, max_per_page=100):
    """
    Validate pagination parameters.

    Args:
        page: Page number.
        per_page: Items per page.
        max_per_page: Maximum allowed per_page.

    Returns:
        Tuple (validated_page, validated_per_page).
    """
    try:
        page = int(page) if page else 1
    except (ValueError, TypeError):
        page = 1

    if page < 1:
        page = 1

    try:
        per_page = int(per_page) if per_page else 15
    except (ValueError, TypeError):
        per_page = 15

    if per_page < 1:
        per_page = 1
    elif per_page > max_per_page:
        per_page = max_per_page

    return page, per_page
