"""
Attachment Analytics Module - Refactored for Database Adapter
Tracking and analyzing attachment performance metrics

✨ Updated: 2025-01-17
- Refactored to use DatabaseAdapter instead of direct sqlite3
- Ready for PostgreSQL migration
- Uses sql_helpers for cross-database compatibility
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING
from collections import defaultdict
import logging
from core.database.sql_helpers import get_date_interval, get_datetime_interval, get_current_timestamp, get_current_date

if TYPE_CHECKING:
    from core.database.database_adapter import DatabaseAdapter

logger = logging.getLogger(__name__)

class AttachmentAnalytics:
    """
    Main class for attachment performance analytics
    
    ✨ Refactored to use DatabaseAdapter for multi-backend support
    """
    
    def __init__(self, db_adapter: 'DatabaseAdapter'):
        """
        Initialize analytics module
        
        Args:
            db_adapter: DatabaseAdapter instance (required)
        """
        if db_adapter is None:
            raise ValueError("db_adapter is required for AttachmentAnalytics")
        
        self.db = db_adapter
        
        # Validate adapter has pooled methods
        if not hasattr(self.db, 'get_connection') or not hasattr(self.db, 'transaction'):
            raise ValueError("DatabaseAdapter must support pooled get_connection()/transaction()")
        
        logger.info("AttachmentAnalytics initialized with DatabaseAdapter")
        
    def track_view(self, attachment_id: int, user_id: int = None, session_id: str = None) -> bool:
        """
        Track attachment view
        
        Args:
            attachment_id: ID of attachment viewed
            user_id: User who viewed (optional)
            session_id: Session ID for grouping (optional)
            
        Returns:
            Success status
        """
        return self._track_action(attachment_id, 'view', user_id, session_id)
        
    def track_click(self, attachment_id: int, user_id: int = None, session_id: str = None) -> bool:
        """Track attachment click/selection"""
        return self._track_action(attachment_id, 'click', user_id, session_id)
        
    def track_share(self, attachment_id: int, user_id: int = None, session_id: str = None) -> bool:
        """Track attachment share"""
        return self._track_action(attachment_id, 'share', user_id, session_id)
        
    def track_copy(self, attachment_id: int, user_id: int = None, session_id: str = None) -> bool:
        """Track attachment copy (e.g., code copy)"""
        return self._track_action(attachment_id, 'copy', user_id, session_id)
        
    def track_rating(self, attachment_id: int, user_id: int, rating: int) -> bool:
        """
        Track user rating for attachment
        
        Args:
            attachment_id: ID of attachment
            user_id: User giving rating
            rating: Rating value (1-5)
            
        Returns:
            Success status
        """
        if not 1 <= rating <= 5:
            logger.error(f"Invalid rating value: {rating}")
            return False
            
        metadata = json.dumps({'rating': rating})
        success = self._track_action(attachment_id, 'rate', user_id, metadata=metadata)
        
        if success:
            # Update user engagement table
            self._update_user_engagement(user_id, attachment_id, rating=rating)
            
        return success
        
    def _track_action(self, attachment_id: int, action_type: str, user_id: int = None, 
                     session_id: str = None, metadata: str = None) -> bool:
        """
        Internal method to track any action
        
        Args:
            attachment_id: ID of attachment
            action_type: Type of action (view, click, share, etc.)
            user_id: User performing action
            session_id: Session ID
            metadata: Extra data as JSON string
            
        Returns:
            Success status
        """
        try:
            # استفاده از connection از pool
            with self.db.transaction() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO attachment_metrics (
                        attachment_id, user_id, action_type, 
                        session_id, metadata
                    ) VALUES (%s, %s, %s, %s, %s)
                """, (attachment_id, user_id, action_type, session_id, metadata))
                
                # Update attachment total counts
                if action_type == 'view':
                    cursor.execute(
                        "UPDATE attachments SET total_views = total_views + 1 WHERE id = %s",
                        (attachment_id,)
                    )
                elif action_type == 'click':
                    cursor.execute(
                        "UPDATE attachments SET total_clicks = total_clicks + 1 WHERE id = %s",
                        (attachment_id,)
                    )
                    
                # Update user engagement if user_id provided
                if user_id:
                    self._update_user_engagement(user_id, attachment_id, action_type, conn)
            
            return True
            
        except Exception as e:
            logger.error(f"Error tracking action: {e}")
            return False
            
    def _update_user_engagement(self, user_id: int, attachment_id: int, 
                               action_type: str = None, conn = None, rating: int = None) -> None:
        """
        Update user engagement metrics
        
        Args:
            user_id: User ID
            attachment_id: Attachment ID
            action_type: Type of action ('view', 'click', etc.)
            conn: Existing connection (if called within transaction) or None
            rating: Rating value (1-5) if applicable
        """
        # ✅ Fixed: استفاده از transaction context manager برای جلوگیری از connection leak
        try:
            # اگر connection از بیرون آمده، از همان استفاده کن
            if conn is not None:
                cursor = conn.cursor()
                try:
                    self._execute_engagement_update(cursor, user_id, attachment_id, action_type, rating)
                finally:
                    cursor.close()
            else:
                # استفاده از transaction context manager
                with self.db.transaction() as trans_conn:
                    cursor = trans_conn.cursor()
                    try:
                        self._execute_engagement_update(cursor, user_id, attachment_id, action_type, rating)
                    finally:
                        cursor.close()
                    # commit اتوماتیک توسط context manager
                        
        except Exception as e:
            logger.error(f"Error updating user engagement: {e}")
            # rollback اتوماتیک توسط context manager در صورت exception
            
    def _execute_engagement_update(self, cursor, user_id: int, attachment_id: int, 
                                   action_type: str = None, rating: int = None):
        """Helper method برای اجرای update (جدا شده برای code reuse)"""
        # Check if engagement record exists
        cursor.execute("""
            SELECT total_views, total_clicks 
            FROM user_attachment_engagement
            WHERE user_id = %s AND attachment_id = %s
        """, (user_id, attachment_id))
        
        existing = cursor.fetchone()
        
        if existing:
            # Update existing record با COALESCE برای NULL safety
            updates = []
            params = []
            
            if action_type == 'view':
                updates.append("total_views = COALESCE(total_views, 0) + 1")
                updates.append("last_view_date = CURRENT_TIMESTAMP")
            elif action_type == 'click':
                updates.append("total_clicks = COALESCE(total_clicks, 0) + 1")
                updates.append("last_view_date = CURRENT_TIMESTAMP")
                
            if rating is not None:
                updates.append("rating = %s")
                params.append(rating)
                
            if updates:
                sql = f"""
                    UPDATE user_attachment_engagement 
                    SET {', '.join(updates)}
                    WHERE user_id = %s AND attachment_id = %s
                """
                params.extend([user_id, attachment_id])
                cursor.execute(sql, params)
        else:
            # Create new record
            cursor.execute("""
                INSERT INTO user_attachment_engagement (
                    user_id, attachment_id, first_view_date, 
                    last_view_date, total_views, total_clicks, rating
                ) VALUES (%s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, %s, %s, %s)
            """, (
                user_id, attachment_id,
                1 if action_type == 'view' else 0,
                1 if action_type == 'click' else 0,
                rating
            ))
            
    def get_attachment_stats(self, attachment_id: int, days: int = 30) -> Dict:
        """
        Get statistics for specific attachment
        
        Args:
            attachment_id: ID of attachment
            days: Number of days to look back
            
        Returns:
            Dictionary with statistics
        """
        stats = {
            'attachment_id': attachment_id,
            'period_days': days,
            'total_views': 0,
            'total_clicks': 0,
            'total_shares': 0,
            'unique_users': 0,
            'engagement_rate': 0,
            'avg_rating': 0,
            'daily_stats': [],
            'top_users': []
        }
        # Clamp period to a reasonable range to avoid extreme queries
        try:
            days = int(days)
        except Exception:
            days = 30
        days = max(1, min(days, 365))
        stats['period_days'] = days
        
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                # Get basic metrics
                # استفاده از sql_helpers برای cross-database compatibility
                date_filter = get_date_interval(days)
                cursor.execute(f"""
                    SELECT 
                        COUNT(CASE WHEN action_type = 'view' THEN 1 END) as views,
                        COUNT(CASE WHEN action_type = 'click' THEN 1 END) as clicks,
                        COUNT(CASE WHEN action_type = 'share' THEN 1 END) as shares,
                        COUNT(DISTINCT user_id) as unique_users,
                        COUNT(CASE WHEN action_type = 'copy' THEN 1 END) as copies
                    FROM attachment_metrics
                    WHERE attachment_id = %s
                    AND DATE(action_date) >= {date_filter}
                """, (attachment_id,))
                
                result = cursor.fetchone()
                if result:
                    stats['total_views'] = result['views']
                    stats['total_clicks'] = result['clicks']
                    stats['total_shares'] = result['shares']
                    stats['unique_users'] = result['unique_users']
                    
                    if stats['total_views'] > 0:
                        stats['engagement_rate'] = (float(stats['total_clicks']) / float(stats['total_views'])) * 100
                
                # Get average rating
                cursor.execute("""
                    SELECT AVG(rating) 
                    FROM user_attachment_engagement
                    WHERE attachment_id = %s AND rating IS NOT NULL
                """, (attachment_id,))
                
                result = cursor.fetchone()
                avg_rating = result['avg'] if result and result.get('avg') else None
                stats['avg_rating'] = round(avg_rating, 2) if avg_rating else 0
                
                # Get daily breakdown
                date_filter = get_date_interval(days)
                cursor.execute(f"""
                    SELECT 
                        DATE(action_date) as date,
                        COUNT(CASE WHEN action_type = 'view' THEN 1 END) as views,
                        COUNT(CASE WHEN action_type = 'click' THEN 1 END) as clicks,
                        COUNT(DISTINCT user_id) as users
                    FROM attachment_metrics
                    WHERE attachment_id = %s
                    AND DATE(action_date) >= {date_filter}
                    GROUP BY DATE(action_date)
                    ORDER BY date DESC
                    LIMIT 7
                """, (attachment_id,))
                
                for row in cursor.fetchall():
                    stats['daily_stats'].append({
                        'date': row['date'],
                        'views': row['views'],
                        'clicks': row['clicks'],
                        'users': row['users']
                    })
                    
                # Get top users
                cursor.execute("""
                    SELECT 
                        u.username,
                        uae.total_views,
                        uae.total_clicks,
                        uae.rating
                    FROM user_attachment_engagement uae
                    LEFT JOIN users u ON uae.user_id = u.user_id
                    WHERE uae.attachment_id = %s
                    ORDER BY uae.total_views DESC
                    LIMIT 5
                """, (attachment_id,))
                
                for row in cursor.fetchall():
                    stats['top_users'].append({
                        'username': row['username'] or 'Unknown',
                        'views': row['total_views'],
                        'clicks': row['total_clicks'],
                        'rating': row['rating']
                    })
                
        except Exception as e:
            logger.error(f"Error getting attachment stats: {e}")
            
        return stats
        
    def get_weapon_stats(self, weapon_id: int, mode: str = 'mp') -> Dict:
        """
        Get aggregated statistics for all attachments of a weapon
        
        Args:
            weapon_id: ID of weapon
            mode: Game mode (mp or br)
            
        Returns:
            Dictionary with weapon-level statistics
        """
        stats = {
            'weapon_id': weapon_id,
            'mode': mode,
            'total_attachments': 0,
            'total_views': 0,
            'total_interactions': 0,
            'top_attachments': [],
            'bottom_attachments': []
        }
        
        try:
            # Get attachment performance for this weapon
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        a.id,
                        a.name,
                        a.code,
                        a.total_views,
                        a.total_clicks,
                        a.avg_rating,
                        ap.popularity_score,
                        ap.engagement_rate
                    FROM attachments a
                    LEFT JOIN attachment_performance ap ON a.id = ap.attachment_id
                    WHERE a.weapon_id = %s AND a.mode = %s
                    ORDER BY a.total_views DESC
                """, (weapon_id, mode))
                
                attachments = cursor.fetchall()
                stats['total_attachments'] = len(attachments)
                
                for att in attachments:
                    stats['total_views'] += att['total_views'] or 0
                    stats['total_interactions'] += (att['total_views'] or 0) + (att['total_clicks'] or 0)
                
                # Get top 5 performers
                if attachments:
                    for att in attachments[:5]:
                        stats['top_attachments'].append({
                            'id': att['id'],
                            'name': att['name'],
                            'code': att['code'],
                            'views': att['total_views'] or 0,
                            'clicks': att['total_clicks'] or 0,
                            'rating': att['avg_rating'] or 0,
                            'popularity': att['popularity_score'] or 0
                        })
                        
                    # Get bottom 3 performers
                    for att in attachments[-3:]:
                        stats['bottom_attachments'].append({
                            'id': att['id'],
                            'name': att['name'],
                            'code': att['code'],
                            'views': att['total_views'] or 0
                        })
                
        except Exception as e:
            logger.error(f"Error getting weapon stats: {e}")
            
        return stats
        
    def calculate_performance_scores(self) -> None:
        """
        Calculate and update performance scores for all attachments
        Should be run periodically (e.g., daily)
        """
        try:
            with self.db.transaction() as conn:
                cursor = conn.cursor()
                
                # Get all attachments with recent activity
                date_filter = get_date_interval(7)
                cursor.execute(f"""
                    SELECT DISTINCT a.id
                    FROM attachments a
                    JOIN attachment_metrics am ON a.id = am.attachment_id
                    WHERE DATE(am.action_date) >= {date_filter}
                """)
                
                attachment_ids = [row['id'] for row in cursor.fetchall()]
                
                for att_id in attachment_ids:
                    scores = self._calculate_single_attachment_scores(att_id)
                    
                    # Insert or update performance record
                    current_date = get_current_date()
                    cursor.execute(f"""
                        INSERT INTO attachment_performance (
                            attachment_id, performance_date,
                            popularity_score, trending_score,
                            engagement_rate, quality_score
                        ) VALUES (%s, {current_date}, %s, %s, %s, %s)
                        ON CONFLICT (attachment_id, performance_date)
                        DO UPDATE SET
                            popularity_score = EXCLUDED.popularity_score,
                            trending_score = EXCLUDED.trending_score,
                            engagement_rate = EXCLUDED.engagement_rate,
                            quality_score = EXCLUDED.quality_score
                    """, (
                        att_id,
                        scores['popularity'],
                        scores['trending'],
                        scores['engagement'],
                        scores['quality']
                    ))
                    
                # Update rankings
                self._update_rankings(cursor)
                
                logger.info(f"✅ Updated performance scores for {len(attachment_ids)} attachments")
                
        except Exception as e:
            logger.error(f"Error calculating performance scores: {e}")
            
    def _calculate_single_attachment_scores(self, attachment_id: int) -> Dict:
        """Calculate performance scores for single attachment"""
        scores = {
            'popularity': 0,
            'trending': 0,
            'engagement': 0,
            'quality': 0
        }
        
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                # Popularity score (based on total views and unique users)
                date_filter = get_date_interval(30)
                cursor.execute(f"""
                    SELECT 
                        COUNT(*) as total_actions,
                        COUNT(DISTINCT user_id) as unique_users,
                        COUNT(CASE WHEN action_type = 'view' THEN 1 END) as views,
                        COUNT(CASE WHEN action_type = 'click' THEN 1 END) as clicks,
                        COUNT(CASE WHEN action_type = 'share' THEN 1 END) as shares
                    FROM attachment_metrics
                    WHERE attachment_id = %s
                    AND DATE(action_date) >= {date_filter}
                """, (attachment_id,))
                
                result = cursor.fetchone()
                if result:
                    total = result['total_actions']
                    users = result['unique_users']
                    views = result['views']
                    clicks = result['clicks']
                    shares = result['shares']
                    
                    # Popularity = weighted combination
                    scores['popularity'] = (
                        (views * 1) + 
                        (clicks * 3) + 
                        (shares * 5) + 
                        (users * 2)
                    ) / 10
                    
                    # Engagement rate
                    if views > 0:
                        scores['engagement'] = ((clicks + shares) / views) * 100
                
                # Trending score (growth rate)
                date_filter_7 = get_date_interval(7)
                date_filter_14 = get_date_interval(14)
                date_filter_8 = get_date_interval(8)
                cursor.execute(f"""
                    SELECT 
                        COUNT(CASE WHEN DATE(action_date) >= {date_filter_7} THEN 1 END) as recent,
                        COUNT(CASE WHEN DATE(action_date) BETWEEN {date_filter_14} AND {date_filter_8} THEN 1 END) as previous
                    FROM attachment_metrics
                    WHERE attachment_id = %s
                """, (attachment_id,))
                
                result = cursor.fetchone()
                recent = result['recent'] if result else 0
                previous = result['previous'] if result else 0
                if previous > 0:
                    growth_rate = ((recent - previous) / previous) * 100
                    scores['trending'] = max(0, min(100, growth_rate))
                elif recent > 0:
                    scores['trending'] = 50  # New trending item
                    
                # Quality score (based on ratings and flags)
                cursor.execute("""
                    SELECT 
                        AVG(rating) as avg_rating,
                        COUNT(rating) as rating_count
                    FROM user_attachment_engagement
                    WHERE attachment_id = %s AND rating IS NOT NULL
                """, (attachment_id,))
                
                result = cursor.fetchone()
                avg_rating = result['avg_rating'] if result and result.get('avg_rating') else None
                rating_count = result['rating_count'] if result and result.get('rating_count') else 0
                if avg_rating:
                    # Weight by number of ratings
                    weight = min(1.0, float(rating_count) / 10)
                    scores['quality'] = (float(avg_rating) / 5) * 100 * weight
                    
                # Bonus for top/seasonal flags
                cursor.execute("""
                    SELECT is_top, is_season_top
                    FROM attachments
                    WHERE id = %s
                """, (attachment_id,))
                
                result = cursor.fetchone()
                is_top = bool(result['is_top']) if result else False
                is_season_top = bool(result['is_season_top']) if result else False
                if is_top:
                    scores['quality'] = min(100, scores['quality'] + 10)
                if is_season_top:
                    scores['quality'] = min(100, scores['quality'] + 15)
                
        except Exception as e:
            logger.error(f"Error calculating scores for attachment {attachment_id}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            
        return scores
        
    def _update_rankings(self, cursor) -> None:
        """Update attachment rankings within weapon, category, and overall"""
        
        current_date = get_current_date()
        
        # Rank within weapon
        cursor.execute(f"""
            WITH RankedAttachments AS (
                SELECT 
                    a.id,
                    a.weapon_id,
                    ap.popularity_score,
                    ROW_NUMBER() OVER (
                        PARTITION BY a.weapon_id 
                        ORDER BY ap.popularity_score DESC
                    ) as weapon_rank
                FROM attachments a
                JOIN attachment_performance ap ON a.id = ap.attachment_id
                WHERE ap.performance_date = {current_date}
            )
            UPDATE attachment_performance
            SET rank_in_weapon = (
                SELECT weapon_rank 
                FROM RankedAttachments 
                WHERE RankedAttachments.id = attachment_performance.attachment_id
            )
            WHERE performance_date = {current_date}
        """)
        
        # Rank overall
        cursor.execute(f"""
            WITH RankedAttachments AS (
                SELECT 
                    attachment_id,
                    popularity_score,
                    ROW_NUMBER() OVER (ORDER BY popularity_score DESC) as overall_rank
                FROM attachment_performance
                WHERE performance_date = {current_date}
            )
            UPDATE attachment_performance
            SET rank_overall = (
                SELECT overall_rank 
                FROM RankedAttachments 
                WHERE RankedAttachments.attachment_id = attachment_performance.attachment_id
            )
            WHERE performance_date = {current_date}
        """)
        
    def get_trending_attachments(self, limit: int = 10) -> List[Dict]:
        """Get currently trending attachments"""
        trending = []
        # Clamp limit to avoid excessive result sets
        try:
            limit = int(limit)
        except Exception:
            limit = 10
        limit = max(1, min(limit, 100))
        
        try:
            current_date = get_current_date()
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT 
                        a.id,
                        a.name,
                        a.code,
                        w.name as weapon_name,
                        wc.name as category_name,
                        ap.trending_score,
                        ap.popularity_score,
                        a.total_views
                    FROM attachment_performance ap
                    JOIN attachments a ON ap.attachment_id = a.id
                    JOIN weapons w ON a.weapon_id = w.id
                    JOIN weapon_categories wc ON w.category_id = wc.id
                    WHERE ap.performance_date = {current_date}
                    AND ap.trending_score > 0
                    AND a.name NOT LIKE '%%Test%%'
                    AND a.name NOT LIKE '%%test%%'
                    AND a.name NOT LIKE 'Attachment %%'
                    AND a.code NOT LIKE 'CODE%%'
                    AND w.name NOT LIKE '%%Test%%'
                    ORDER BY ap.trending_score DESC
                    LIMIT %s
                """, (limit,))
                
                for row in cursor.fetchall():
                    trending.append({
                        'id': row['id'],
                        'name': row['name'],
                        'code': row['code'],
                        'weapon': row['weapon_name'],
                        'category': row['category_name'],
                        'trending_score': row['trending_score'],
                        'popularity_score': row['popularity_score'],
                        'total_views': row['total_views']
                    })
                
        except Exception as e:
            logger.error(f"Error getting trending attachments: {e}")
            
        return trending
        
    def get_underperforming_attachments(self, limit: int = 10) -> List[Dict]:
        """
        Get attachments that need attention
        Uses ONLY existing data without dependency on attachment_performance table
        
        Criteria for underperforming:
        1. No Image: Missing image_file_id
        2. Low Views: < 50 views (reasonable threshold)
        3. Low Engagement: Click rate < 5% AND has views > 20
        """
        underperforming = []
        # Clamp limit to avoid excessive processing
        try:
            limit = int(limit)
        except Exception:
            limit = 10
        limit = max(1, min(limit, 200))
        
        try:
            # Use pooled connection via context manager (psycopg3)
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                # Get average views for comparison
                cursor.execute("SELECT AVG(total_views) as avg FROM attachments WHERE total_views > 0")
                result = cursor.fetchone()
                avg_views = float(result['avg']) if result and result.get('avg') else 100.0
                threshold = max(50, avg_views * 0.3)  # 30% of average or minimum 50
                
                cursor.execute("""
                    SELECT 
                        a.id,
                        a.name,
                        a.code,
                        COALESCE(w.name, 'Unknown') as weapon_name,
                        a.total_views,
                        a.total_clicks,
                        CASE 
                            WHEN a.image_file_id IS NULL THEN 'No Image'
                            WHEN a.total_views < %s THEN 'Low Views'
                            WHEN a.total_views >= 20 AND 
                                 CAST(a.total_clicks AS REAL) / NULLIF(a.total_views, 0) * 100 < 5.0 
                                 THEN 'Low Engagement'
                            ELSE 'Other'
                        END as issue,
                        CASE 
                            WHEN a.image_file_id IS NULL THEN 3
                            WHEN a.total_views < %s THEN 2
                            ELSE 1
                        END as priority
                    FROM attachments a
                    LEFT JOIN weapons w ON a.weapon_id = w.id
                    WHERE 
                        (
                            a.image_file_id IS NULL
                            OR a.total_views < %s
                            OR (
                                a.total_views >= 20 
                                AND CAST(a.total_clicks AS REAL) / NULLIF(a.total_views, 0) * 100 < 5.0
                            )
                        )
                        AND a.name NOT LIKE '%%Test%%'
                        AND a.name NOT LIKE '%%test%%'
                        AND a.name NOT LIKE '%%تست%%'
                        AND a.name NOT LIKE '%%وکسورت%%'
                        AND a.name NOT LIKE 'Attachment %%'
                        AND a.code NOT LIKE 'CODE%%'
                        AND a.code NOT LIKE 'DUP%%'
                        AND a.code NOT LIKE '%%TEST%%'
                        AND a.code NOT LIKE '%%ONLY%%'
                        AND a.code NOT LIKE '%%تست%%'
                        AND a.code NOT LIKE '%%test%%'
                        AND COALESCE(w.name, '') NOT LIKE '%%Test%%'
                        AND COALESCE(w.name, '') NOT LIKE '%%Validation%%'
                    ORDER BY priority DESC, a.total_views ASC
                    LIMIT %s
                """, (threshold, threshold, threshold, limit * 2))  # Get more for filtering
                
                seen = set()
                for row in cursor.fetchall():
                    att_id = row['id']
                    if att_id not in seen and len(underperforming) < limit:
                        seen.add(att_id)
                        underperforming.append({
                            'id': att_id,
                            'name': row['name'],
                            'code': row['code'],
                            'weapon': row['weapon_name'],
                            'views': row['total_views'] or 0,
                            'clicks': row['total_clicks'] or 0,
                            'issue': row['issue'],
                            'priority': row['priority']
                        })
                
        except Exception as e:
            logger.error(f"Error getting underperforming attachments: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            
        return underperforming
