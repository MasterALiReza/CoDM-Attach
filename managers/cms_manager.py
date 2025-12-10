from typing import List, Dict, Optional, Any
from datetime import datetime
import json


class CMSManager:
    """
    Content Management operations backed by PostgreSQL via DatabaseAdapter.
    Table: cms_content (ensured by core.database.database_pg._ensure_schema)
    """

    def __init__(self, db):
        self.db = db

    # ========== Create / Update / State Transitions ==========
    def create_content(
        self,
        content_type: str,
        title: str,
        body: str,
        author_id: int,
        tags: Optional[List[str]] = None,
    ) -> Optional[int]:
        """
        Create a new content entry and return content_id
        """
        tags = tags or []
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO cms_content (content_type, title, body, author_id, tags)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                RETURNING content_id
                """,
                (content_type, title, body, author_id, json.dumps(tags)),
            )
            row = cur.fetchone()
            conn.commit()
            return row["content_id"] if row and isinstance(row, dict) else (row[0] if row else None)

    def update_content(
        self,
        content_id: int,
        *,
        title: Optional[str] = None,
        body: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: Optional[str] = None,
    ) -> bool:
        """
        Update fields of a content. Only provided fields are updated.
        """
        sets = []
        params: List[Any] = []
        if title is not None:
            sets.append("title = %s")
            params.append(title)
        if body is not None:
            sets.append("body = %s")
            params.append(body)
        if tags is not None:
            sets.append("tags = %s::jsonb")
            params.append(json.dumps(tags))
        if status is not None:
            sets.append("status = %s")
            params.append(status)
        # Always bump updated_at
        sets.append("updated_at = NOW()")
        if not sets:
            return True
        params.append(content_id)
        query = f"UPDATE cms_content SET {', '.join(sets)} WHERE content_id = %s"
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, tuple(params))
            conn.commit()
            return cur.rowcount > 0

    def publish_content(self, content_id: int) -> bool:
        """
        Set status to 'published' and set published_at
        """
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE cms_content
                SET status = 'published', published_at = NOW(), updated_at = NOW()
                WHERE content_id = %s
                """,
                (content_id,),
            )
            conn.commit()
            return cur.rowcount > 0

    def archive_content(self, content_id: int) -> bool:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE cms_content
                SET status = 'archived', updated_at = NOW()
                WHERE content_id = %s
                """,
                (content_id,),
            )
            conn.commit()
            return cur.rowcount > 0

    def delete_content(self, content_id: int, hard: bool = False) -> bool:
        """
        Archive by default. If hard=True, delete row.
        """
        if not hard:
            return self.archive_content(content_id)
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM cms_content WHERE content_id = %s", (content_id,))
            conn.commit()
            return cur.rowcount > 0

    # ========== Read / List / Search ==========
    def get_content(self, content_id: int) -> Optional[Dict]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT content_id, content_type, title, body, tags, author_id,
                       status, created_at, updated_at, published_at
                FROM cms_content
                WHERE content_id = %s
                """,
                (content_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def get_published_content(self, content_type: Optional[str] = None, limit: int = 10, offset: int = 0) -> List[Dict]:
        query = (
            "SELECT content_id, content_type, title, body, tags, published_at "
            "FROM cms_content WHERE status = 'published'"
        )
        params: List[Any] = []
        if content_type:
            query += " AND content_type = %s"
            params.append(content_type)
        query += " ORDER BY published_at DESC NULLS LAST LIMIT %s OFFSET %s"
        params.append(limit)
        params.append(offset)
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, tuple(params))
            rows = cur.fetchall() or []
            return [dict(r) for r in rows]

    def count_published_content(self, content_type: Optional[str] = None) -> int:
        """Count total published contents, optionally filtered by type."""
        query = "SELECT COUNT(*) AS c FROM cms_content WHERE status = 'published'"
        params: List[Any] = []
        if content_type:
            query += " AND content_type = %s"
            params.append(content_type)
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, tuple(params))
            row = cur.fetchone()
            if not row:
                return 0
            # row could be dict-like or tuple
            try:
                return int(row.get('c'))  # type: ignore[union-attr]
            except Exception:
                return int(row[0])

    def list_content(
        self,
        *,
        content_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None,
        tag: Optional[str] = None,
        order_desc: bool = True,
    ) -> List[Dict]:
        """
        List contents with optional filters and simple search.
        """
        clauses = ["1=1"]
        params: List[Any] = []
        if content_type:
            clauses.append("content_type = %s")
            params.append(content_type)
        if status:
            clauses.append("status = %s")
            params.append(status)
        if search:
            like = f"%{search}%"
            clauses.append("(title ILIKE %s OR body ILIKE %s)")
            params.extend([like, like])
        if tag:
            # tags @> '["tag"]'
            clauses.append("tags @> %s::jsonb")
            params.append(json.dumps([tag]))
        order = "DESC" if order_desc else "ASC"
        query = (
            "SELECT content_id, content_type, title, body, tags, author_id, status, "
            "created_at, updated_at, published_at "
            f"FROM cms_content WHERE {' AND '.join(clauses)} "
            f"ORDER BY COALESCE(published_at, updated_at) {order} LIMIT %s OFFSET %s"
        )
        params.extend([limit, offset])
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, tuple(params))
            rows = cur.fetchall() or []
            return [dict(r) for r in rows]

    def add_tag(self, content_id: int, tag: str) -> bool:
        item = self.get_content(content_id)
        if not item:
            return False
        tags = item.get("tags") or []
        if tag not in tags:
            tags.append(tag)
        return self.update_content(content_id, tags=tags)

    def remove_tag(self, content_id: int, tag: str) -> bool:
        item = self.get_content(content_id)
        if not item:
            return False
        tags = [t for t in (item.get("tags") or []) if t != tag]
        return self.update_content(content_id, tags=tags)

    def search_content(self, query: str, limit: int = 20) -> List[Dict]:
        """
        Simple search in title/body; returns most recent first.
        """
        like = f"%{query}%"
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT content_id, content_type, title, body, tags, status, published_at, updated_at
                FROM cms_content
                WHERE title ILIKE %s OR body ILIKE %s
                ORDER BY COALESCE(published_at, updated_at) DESC
                LIMIT %s
                """,
                (like, like, limit),
            )
            rows = cur.fetchall() or []
            return [dict(r) for r in rows]
