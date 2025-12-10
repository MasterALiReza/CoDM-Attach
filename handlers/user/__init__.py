"""User Handlers - اصلی (ماژولار شده!)"""

# Define conversation states directly here to avoid circular imports or dependency on aggregator
SELECTING_CATEGORY = 0
SELECTING_WEAPON = 1
VIEWING_ATTACHMENTS = 2
SEARCHING = 3

__all__ = ['SEARCHING', 'SELECTING_CATEGORY', 'SELECTING_WEAPON', 'VIEWING_ATTACHMENTS']
