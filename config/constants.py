"""
تنظیمات ثابت (Constants) پروژه
جایگزین Magic Numbers برای بهبود خوانایی و نگهداری کد
"""

# ====================================
# Validation Constants
# ====================================

# Attachment
MAX_ATTACHMENT_CODE_LENGTH = 50
MIN_ATTACHMENT_CODE_LENGTH = 3
MAX_ATTACHMENT_NAME_LENGTH = 100
MIN_ATTACHMENT_NAME_LENGTH = 2

# Text Content
MAX_COMMENT_LENGTH = 500
MAX_TICKET_SUBJECT_LENGTH = 200
MAX_TICKET_DESCRIPTION_LENGTH = 2000
MAX_FAQ_QUESTION_LENGTH = 200
MAX_FAQ_ANSWER_LENGTH = 2000
MAX_BROADCAST_MESSAGE_LENGTH = 4000

# Image
MAX_IMAGE_SIZE_MB = 10
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {'jpg', 'jpeg', 'png', 'webp'}

# Video
MAX_VIDEO_SIZE_MB = 20
MAX_VIDEO_SIZE_BYTES = MAX_VIDEO_SIZE_MB * 1024 * 1024
ALLOWED_VIDEO_FORMATS = {'mp4', 'avi', 'mov', 'mkv'}

# ====================================
# Cache TTL (Time To Live) - seconds
# ====================================

CACHE_TTL_CATEGORIES = 3600      # 1 hour
CACHE_TTL_WEAPONS = 1800         # 30 minutes
CACHE_TTL_ATTACHMENTS = 300      # 5 minutes
CACHE_TTL_USERS = 600            # 10 minutes
CACHE_TTL_CHANNEL_MEMBER = 1800  # 30 minutes (for members)
CACHE_TTL_CHANNEL_NON_MEMBER = 120  # 2 minutes (for non-members)
CACHE_TTL_CATEGORY_COUNTS = 1800  # 30 minutes

# Cache Limits
CACHE_MAX_SIZE = 10000  # Maximum cache entries (LRU eviction)

# ====================================
# Performance Thresholds
# ====================================

SLOW_QUERY_THRESHOLD_MS = 100  # 100ms
SLOW_QUERY_THRESHOLD_SEC = SLOW_QUERY_THRESHOLD_MS / 1000  # 0.1 seconds

# ====================================
# Broadcasting & Batch Operations
# ====================================

BROADCAST_BATCH_SIZE = 30
BROADCAST_DELAY_SECONDS = 0.05  # 50ms between batches
NOTIFICATION_BATCH_DELAY_SECONDS = 5  # Combine notifications within 5 seconds

# ====================================
# Database Connection Pool
# ====================================

DB_POOL_SIZE = 20
DB_POOL_MAX_OVERFLOW = 10
DB_POOL_TIMEOUT_SECONDS = 30

# ====================================
# Pagination
# ====================================

ITEMS_PER_PAGE = 10
MAX_ITEMS_PER_PAGE = 50

# ====================================
# Search
# ====================================

FUZZY_SEARCH_THRESHOLD = 60  # Minimum similarity score (0-100)
SEARCH_MAX_RESULTS = 50

# ====================================
# Rate Limiting
# ====================================

RATE_LIMIT_MESSAGES_PER_MINUTE = 20
RATE_LIMIT_SEARCHES_PER_MINUTE = 10
RATE_LIMIT_FEEDBACK_PER_HOUR = 50

# ====================================
# Analytics & Backup
# ====================================

BACKUP_RETENTION_COUNT = 10  # Keep last 10 backups
ANALYTICS_DAILY_RETENTION_DAYS = 90  # 3 months
ANALYTICS_EXPORT_MAX_ROWS = 100000

# ====================================
# Ticket System
# ====================================

TICKET_AUTO_CLOSE_DAYS = 30  # Auto-close inactive tickets after 30 days
TICKET_REPLY_MAX_LENGTH = 1000

# ====================================
# Logging
# ====================================

LOG_MAX_FILE_SIZE_MB = 10
LOG_BACKUP_COUNT = 5
LOG_ROTATION_INTERVAL_DAYS = 7
