"""PostgreSQL implementation of PolicyRepository."""

from typing import List, Optional, Tuple
from uuid import UUID
from asyncpg import Pool
import json

from src.domain.ports.policy_repository import PolicyRepository
from src.domain.models.policy_models import (
    Policy, PolicyDocument, PolicyVersion, PolicyAccess,
    Questionnaire, Question, QuestionAttempt,
    PolicyStatus, AccessLevel, QuestionType, ContentFormat
)


class PostgresPolicyRepository(PolicyRepository):
    """PostgreSQL adapter for policy management."""

    def __init__(self, pool: Pool):
        """
        Initialize repository.

        Args:
            pool: AsyncPG connection pool
        """
        self.pool = pool

    # ============================================
    # POLICY CRUD
    # ============================================

    async def create_policy(
        self,
        owner_user_id: str,
        title: str,
        description: Optional[str] = None,
        access_level: AccessLevel = AccessLevel.PRIVATE,
        metadata: Optional[dict] = None
    ) -> Policy:
        """Create a new policy."""
        query = """
            INSERT INTO policies (
                owner_user_id, title, description, access_level, metadata
            )
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                owner_user_id,
                title,
                description,
                access_level.value,
                json.dumps(metadata or {})
            )

            return self._row_to_policy(row)

    async def get_policy_by_id(self, policy_id: UUID) -> Optional[Policy]:
        """Get policy by ID."""
        query = "SELECT * FROM policies WHERE policy_id = $1"

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, policy_id)

            if not row:
                return None

            return self._row_to_policy(row)

    async def update_policy(
        self,
        policy_id: UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
        content: Optional[str] = None,
        content_format: Optional[str] = None,
        status: Optional[PolicyStatus] = None,
        access_level: Optional[AccessLevel] = None,
        editing_session_id: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> Optional[Policy]:
        """Update policy fields."""
        updates = []
        params = []
        param_count = 1

        if title is not None:
            updates.append(f"title = ${param_count}")
            params.append(title)
            param_count += 1

        if description is not None:
            updates.append(f"description = ${param_count}")
            params.append(description)
            param_count += 1

        if content is not None:
            updates.append(f"content = ${param_count}")
            params.append(content)
            param_count += 1

        if content_format is not None:
            updates.append(f"content_format = ${param_count}")
            params.append(content_format)
            param_count += 1

        if status is not None:
            updates.append(f"status = ${param_count}")
            params.append(status.value)
            param_count += 1

            # Set timestamp based on status
            if status == PolicyStatus.APPROVED:
                updates.append("approved_at = NOW()")
            elif status == PolicyStatus.PUBLISHED:
                updates.append("published_at = NOW()")
            elif status == PolicyStatus.ARCHIVED:
                updates.append("archived_at = NOW()")

        if access_level is not None:
            updates.append(f"access_level = ${param_count}")
            params.append(access_level.value)
            param_count += 1

        if editing_session_id is not None:
            updates.append(f"editing_session_id = ${param_count}")
            params.append(editing_session_id)
            param_count += 1

        if metadata is not None:
            updates.append(f"metadata = ${param_count}")
            params.append(json.dumps(metadata))
            param_count += 1

        if not updates:
            return await self.get_policy_by_id(policy_id)

        params.append(policy_id)

        query = f"""
            UPDATE policies
            SET {', '.join(updates)}
            WHERE policy_id = ${param_count}
            RETURNING *
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)

            if not row:
                return None

            return self._row_to_policy(row)

    async def update_policy_artifacts(
        self,
        policy_id: UUID,
        pdf_blob_path: str,
        jpeg_blob_path: str
    ) -> Optional[Policy]:
        """Update generated artifact paths."""
        query = """
            UPDATE policies
            SET pdf_blob_path = $1,
                jpeg_blob_path = $2,
                status = 'published',
                published_at = NOW()
            WHERE policy_id = $3
            RETURNING *
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, pdf_blob_path, jpeg_blob_path, policy_id)

            if not row:
                return None

            return self._row_to_policy(row)

    async def increment_policy_version(
        self,
        policy_id: UUID,
        changed_by_user_id: str,
        change_summary: Optional[str] = None
    ) -> int:
        """Increment policy version and create snapshot."""
        query = """
            UPDATE policies
            SET version = version + 1
            WHERE policy_id = $1
            RETURNING version
        """

        async with self.pool.acquire() as conn:
            new_version = await conn.fetchval(query, policy_id)
            return new_version

    async def list_policies(
        self,
        owner_user_id: Optional[str] = None,
        status: Optional[PolicyStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Policy], int]:
        """List policies with pagination."""
        conditions = []
        params = []
        param_count = 1

        if owner_user_id is not None:
            conditions.append(f"owner_user_id = ${param_count}")
            params.append(owner_user_id)
            param_count += 1

        if status is not None:
            conditions.append(f"status = ${param_count}")
            params.append(status.value)
            param_count += 1

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        count_query = f"SELECT COUNT(*) FROM policies {where_clause}"
        data_query = f"""
            SELECT * FROM policies
            {where_clause}
            ORDER BY updated_at DESC
            LIMIT ${param_count} OFFSET ${param_count + 1}
        """

        params.extend([limit, offset])

        async with self.pool.acquire() as conn:
            total = await conn.fetchval(count_query, *params[:-2]) if params[:-2] else await conn.fetchval(count_query)
            rows = await conn.fetch(data_query, *params)

            policies = [self._row_to_policy(row) for row in rows]

            return policies, total

    async def get_accessible_policies(
        self,
        user_id: str,
        user_groups: List[str],
        status: Optional[PolicyStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Policy], int]:
        """Get policies user can access based on ownership and groups."""
        status_filter = "AND p.status = $4" if status else ""

        count_query = f"""
            SELECT COUNT(DISTINCT p.policy_id)
            FROM policies p
            LEFT JOIN policy_access pa ON p.policy_id = pa.policy_id
            WHERE (
                p.owner_user_id = $1
                OR p.access_level = 'organization'
                OR (p.access_level = 'group' AND pa.group_name = ANY($2) AND pa.can_view = TRUE)
            )
            {status_filter}
        """

        data_query = f"""
            SELECT DISTINCT p.*
            FROM policies p
            LEFT JOIN policy_access pa ON p.policy_id = pa.policy_id
            WHERE (
                p.owner_user_id = $1
                OR p.access_level = 'organization'
                OR (p.access_level = 'group' AND pa.group_name = ANY($2) AND pa.can_view = TRUE)
            )
            {status_filter}
            ORDER BY p.updated_at DESC
            LIMIT $3 OFFSET ${4 if status else 3}
        """

        params = [user_id, user_groups, limit]
        if status:
            params.insert(3, status.value)
        params.append(offset)

        async with self.pool.acquire() as conn:
            count_params = [user_id, user_groups]
            if status:
                count_params.append(status.value)
            total = await conn.fetchval(count_query, *count_params)
            rows = await conn.fetch(data_query, *params)

            policies = [self._row_to_policy(row) for row in rows]

            return policies, total

    async def delete_policy(self, policy_id: UUID) -> bool:
        """Delete policy (CASCADE deletes related data)."""
        query = "DELETE FROM policies WHERE policy_id = $1"

        async with self.pool.acquire() as conn:
            result = await conn.execute(query, policy_id)
            return result == "DELETE 1"

    # ============================================
    # POLICY DOCUMENTS
    # ============================================

    async def add_policy_document(
        self,
        policy_id: UUID,
        filename: str,
        content_type: str,
        size_bytes: int,
        blob_path: str,
        gcs_uri: str,
        display_order: int = 0,
        metadata: Optional[dict] = None
    ) -> PolicyDocument:
        """Add source document to policy."""
        query = """
            INSERT INTO policy_documents (
                policy_id, filename, content_type, size_bytes,
                blob_path, gcs_uri, display_order, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                policy_id,
                filename,
                content_type,
                size_bytes,
                blob_path,
                gcs_uri,
                display_order,
                json.dumps(metadata or {})
            )

            return self._row_to_policy_document(row)

    async def get_policy_documents(self, policy_id: UUID) -> List[PolicyDocument]:
        """Get all documents for a policy."""
        query = """
            SELECT * FROM policy_documents
            WHERE policy_id = $1
            ORDER BY display_order ASC, uploaded_at ASC
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, policy_id)

            return [self._row_to_policy_document(row) for row in rows]

    async def delete_policy_document(self, document_id: UUID) -> bool:
        """Delete a policy document."""
        query = "DELETE FROM policy_documents WHERE document_id = $1"

        async with self.pool.acquire() as conn:
            result = await conn.execute(query, document_id)
            return result == "DELETE 1"

    # ============================================
    # POLICY VERSIONS
    # ============================================

    async def get_policy_versions(
        self,
        policy_id: UUID,
        limit: int = 10
    ) -> List[PolicyVersion]:
        """Get version history for policy."""
        query = """
            SELECT * FROM policy_versions
            WHERE policy_id = $1
            ORDER BY version_number DESC
            LIMIT $2
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, policy_id, limit)

            return [self._row_to_policy_version(row) for row in rows]

    async def get_policy_version(
        self,
        policy_id: UUID,
        version_number: int
    ) -> Optional[PolicyVersion]:
        """Get specific version."""
        query = """
            SELECT * FROM policy_versions
            WHERE policy_id = $1 AND version_number = $2
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, policy_id, version_number)

            if not row:
                return None

            return self._row_to_policy_version(row)

    # ============================================
    # ACCESS CONTROL
    # ============================================

    async def grant_policy_access(
        self,
        policy_id: UUID,
        group_name: str,
        can_view: bool = True,
        can_edit: bool = False,
        can_approve: bool = False,
        granted_by_user_id: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> PolicyAccess:
        """Grant access to Entra ID group."""
        query = """
            INSERT INTO policy_access (
                policy_id, group_name, can_view, can_edit, can_approve,
                granted_by_user_id, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (policy_id, group_name)
            DO UPDATE SET
                can_view = EXCLUDED.can_view,
                can_edit = EXCLUDED.can_edit,
                can_approve = EXCLUDED.can_approve,
                granted_by_user_id = EXCLUDED.granted_by_user_id,
                metadata = EXCLUDED.metadata
            RETURNING *
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                policy_id,
                group_name,
                can_view,
                can_edit,
                can_approve,
                granted_by_user_id,
                json.dumps(metadata or {})
            )

            return self._row_to_policy_access(row)

    async def revoke_policy_access(
        self,
        policy_id: UUID,
        group_name: str
    ) -> bool:
        """Revoke group access."""
        query = """
            DELETE FROM policy_access
            WHERE policy_id = $1 AND group_name = $2
        """

        async with self.pool.acquire() as conn:
            result = await conn.execute(query, policy_id, group_name)
            return result == "DELETE 1"

    async def get_policy_access_list(
        self,
        policy_id: UUID
    ) -> List[PolicyAccess]:
        """Get all access rules for policy."""
        query = """
            SELECT * FROM policy_access
            WHERE policy_id = $1
            ORDER BY granted_at DESC
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, policy_id)

            return [self._row_to_policy_access(row) for row in rows]

    async def check_user_access(
        self,
        policy_id: UUID,
        user_id: str,
        user_groups: List[str]
    ) -> bool:
        """Check if user can access policy."""
        query = "SELECT user_can_access_policy($1, $2, $3)"

        async with self.pool.acquire() as conn:
            result = await conn.fetchval(query, policy_id, user_id, user_groups)
            return result

    # ============================================
    # QUESTIONNAIRES
    # ============================================

    async def create_questionnaire(
        self,
        policy_id: UUID,
        title: str,
        description: Optional[str] = None,
        pass_threshold_percentage: int = 70,
        metadata: Optional[dict] = None
    ) -> Questionnaire:
        """Create questionnaire for policy."""
        query = """
            INSERT INTO questionnaires (
                policy_id, title, description, pass_threshold_percentage, metadata
            )
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                policy_id,
                title,
                description,
                pass_threshold_percentage,
                json.dumps(metadata or {})
            )

            return self._row_to_questionnaire(row)

    async def get_questionnaire_by_policy(
        self,
        policy_id: UUID
    ) -> Optional[Questionnaire]:
        """Get questionnaire for policy."""
        query = "SELECT * FROM questionnaires WHERE policy_id = $1"

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, policy_id)

            if not row:
                return None

            return self._row_to_questionnaire(row)

    async def update_questionnaire(
        self,
        questionnaire_id: UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
        pass_threshold_percentage: Optional[int] = None,
        is_active: Optional[bool] = None
    ) -> Optional[Questionnaire]:
        """Update questionnaire."""
        updates = []
        params = []
        param_count = 1

        if title is not None:
            updates.append(f"title = ${param_count}")
            params.append(title)
            param_count += 1

        if description is not None:
            updates.append(f"description = ${param_count}")
            params.append(description)
            param_count += 1

        if pass_threshold_percentage is not None:
            updates.append(f"pass_threshold_percentage = ${param_count}")
            params.append(pass_threshold_percentage)
            param_count += 1

        if is_active is not None:
            updates.append(f"is_active = ${param_count}")
            params.append(is_active)
            param_count += 1

        if not updates:
            return None

        params.append(questionnaire_id)

        query = f"""
            UPDATE questionnaires
            SET {', '.join(updates)}
            WHERE questionnaire_id = ${param_count}
            RETURNING *
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)

            if not row:
                return None

            return self._row_to_questionnaire(row)

    # ============================================
    # QUESTIONS
    # ============================================

    async def add_question(
        self,
        questionnaire_id: UUID,
        question_text: str,
        question_type: str,
        correct_answer: any,
        options: Optional[List[dict]] = None,
        explanation: Optional[str] = None,
        difficulty: Optional[str] = None,
        points: int = 1,
        display_order: int = 0,
        metadata: Optional[dict] = None
    ) -> Question:
        """Add question to questionnaire."""
        query = """
            INSERT INTO questions (
                questionnaire_id, question_text, question_type, correct_answer,
                options, explanation, difficulty, points, display_order, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING *
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                questionnaire_id,
                question_text,
                question_type,
                json.dumps(correct_answer),
                json.dumps(options) if options else None,
                explanation,
                difficulty,
                points,
                display_order,
                json.dumps(metadata or {})
            )

            return self._row_to_question(row)

    async def update_question(
        self,
        question_id: UUID,
        question_text: Optional[str] = None,
        correct_answer: Optional[any] = None,
        options: Optional[List[dict]] = None,
        explanation: Optional[str] = None,
        difficulty: Optional[str] = None,
        points: Optional[int] = None
    ) -> Optional[Question]:
        """Update question."""
        updates = []
        params = []
        param_count = 1

        if question_text is not None:
            updates.append(f"question_text = ${param_count}")
            params.append(question_text)
            param_count += 1

        if correct_answer is not None:
            updates.append(f"correct_answer = ${param_count}")
            params.append(json.dumps(correct_answer))
            param_count += 1

        if options is not None:
            updates.append(f"options = ${param_count}")
            params.append(json.dumps(options))
            param_count += 1

        if explanation is not None:
            updates.append(f"explanation = ${param_count}")
            params.append(explanation)
            param_count += 1

        if difficulty is not None:
            updates.append(f"difficulty = ${param_count}")
            params.append(difficulty)
            param_count += 1

        if points is not None:
            updates.append(f"points = ${param_count}")
            params.append(points)
            param_count += 1

        if not updates:
            return None

        params.append(question_id)

        query = f"""
            UPDATE questions
            SET {', '.join(updates)}
            WHERE question_id = ${param_count}
            RETURNING *
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)

            if not row:
                return None

            return self._row_to_question(row)

    async def get_questions(
        self,
        questionnaire_id: UUID
    ) -> List[Question]:
        """Get all questions for questionnaire."""
        query = """
            SELECT * FROM questions
            WHERE questionnaire_id = $1
            ORDER BY display_order ASC, created_at ASC
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, questionnaire_id)

            return [self._row_to_question(row) for row in rows]

    async def delete_question(self, question_id: UUID) -> bool:
        """Delete question."""
        query = "DELETE FROM questions WHERE question_id = $1"

        async with self.pool.acquire() as conn:
            result = await conn.execute(query, question_id)
            return result == "DELETE 1"

    # ============================================
    # QUESTION ATTEMPTS
    # ============================================

    async def record_attempt(
        self,
        question_id: UUID,
        user_id: str,
        user_answer: any,
        is_correct: bool,
        time_spent_seconds: Optional[int] = None
    ) -> QuestionAttempt:
        """Record user's answer attempt."""
        query = """
            INSERT INTO question_attempts (
                question_id, user_id, user_answer, is_correct, time_spent_seconds
            )
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                question_id,
                user_id,
                json.dumps(user_answer),
                is_correct,
                time_spent_seconds
            )

            return self._row_to_question_attempt(row)

    async def get_user_attempts(
        self,
        user_id: str,
        questionnaire_id: Optional[UUID] = None,
        limit: int = 100
    ) -> List[QuestionAttempt]:
        """Get user's attempt history."""
        if questionnaire_id:
            query = """
                SELECT qa.* FROM question_attempts qa
                JOIN questions q ON qa.question_id = q.question_id
                WHERE qa.user_id = $1 AND q.questionnaire_id = $2
                ORDER BY qa.attempted_at DESC
                LIMIT $3
            """
            params = [user_id, questionnaire_id, limit]
        else:
            query = """
                SELECT * FROM question_attempts
                WHERE user_id = $1
                ORDER BY attempted_at DESC
                LIMIT $2
            """
            params = [user_id, limit]

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

            return [self._row_to_question_attempt(row) for row in rows]

    # ============================================
    # HELPER METHODS (Row to Model Conversion)
    # ============================================

    def _row_to_policy(self, row) -> Policy:
        """Convert database row to Policy model."""
        return Policy(
            policy_id=row['policy_id'],
            owner_user_id=row['owner_user_id'],
            title=row['title'],
            description=row['description'],
            content=row['content'],
            content_format=ContentFormat(row['content_format']),
            status=PolicyStatus(row['status']),
            access_level=AccessLevel(row['access_level']),
            pdf_blob_path=row['pdf_blob_path'],
            jpeg_blob_path=row['jpeg_blob_path'],
            editing_session_id=row['editing_session_id'],
            metadata=row['metadata'] if isinstance(row['metadata'], dict) else json.loads(row['metadata']) if row['metadata'] else {},
            version=row['version'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            approved_at=row['approved_at'],
            published_at=row['published_at'],
            archived_at=row['archived_at']
        )

    def _row_to_policy_document(self, row) -> PolicyDocument:
        """Convert database row to PolicyDocument model."""
        return PolicyDocument(
            document_id=row['document_id'],
            policy_id=row['policy_id'],
            filename=row['filename'],
            content_type=row['content_type'],
            size_bytes=row['size_bytes'],
            blob_path=row['blob_path'],
            gcs_uri=row['gcs_uri'],
            display_order=row['display_order'],
            metadata=row['metadata'] if isinstance(row['metadata'], dict) else json.loads(row['metadata']) if row['metadata'] else {},
            uploaded_at=row['uploaded_at']
        )

    def _row_to_policy_version(self, row) -> PolicyVersion:
        """Convert database row to PolicyVersion model."""
        return PolicyVersion(
            version_id=row['version_id'],
            policy_id=row['policy_id'],
            version_number=row['version_number'],
            content=row['content'],
            content_format=row['content_format'],
            status=PolicyStatus(row['status']),
            changed_by_user_id=row['changed_by_user_id'],
            change_summary=row['change_summary'],
            metadata=row['metadata'] if isinstance(row['metadata'], dict) else json.loads(row['metadata']) if row['metadata'] else {},
            created_at=row['created_at']
        )

    def _row_to_policy_access(self, row) -> PolicyAccess:
        """Convert database row to PolicyAccess model."""
        return PolicyAccess(
            access_id=row['access_id'],
            policy_id=row['policy_id'],
            group_name=row['group_name'],
            can_view=row['can_view'],
            can_edit=row['can_edit'],
            can_approve=row['can_approve'],
            metadata=row['metadata'] if isinstance(row['metadata'], dict) else json.loads(row['metadata']) if row['metadata'] else {},
            granted_at=row['granted_at'],
            granted_by_user_id=row['granted_by_user_id']
        )

    def _row_to_questionnaire(self, row) -> Questionnaire:
        """Convert database row to Questionnaire model."""
        return Questionnaire(
            questionnaire_id=row['questionnaire_id'],
            policy_id=row['policy_id'],
            title=row['title'],
            description=row['description'],
            pass_threshold_percentage=row['pass_threshold_percentage'],
            randomize_questions=row['randomize_questions'],
            randomize_options=row['randomize_options'],
            is_active=row['is_active'],
            metadata=row['metadata'] if isinstance(row['metadata'], dict) else json.loads(row['metadata']) if row['metadata'] else {},
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

    def _row_to_question(self, row) -> Question:
        """Convert database row to Question model."""
        return Question(
            question_id=row['question_id'],
            questionnaire_id=row['questionnaire_id'],
            question_text=row['question_text'],
            question_type=QuestionType(row['question_type']),
            correct_answer=row['correct_answer'] if isinstance(row['correct_answer'], (dict, list)) else json.loads(row['correct_answer']),
            options=row['options'] if isinstance(row['options'], list) else (json.loads(row['options']) if row['options'] else None),
            explanation=row['explanation'],
            difficulty=row['difficulty'],
            points=row['points'],
            display_order=row['display_order'],
            generated_from_content=row.get('generated_from_content'),
            metadata=row['metadata'] if isinstance(row['metadata'], dict) else json.loads(row['metadata']) if row['metadata'] else {},
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

    def _row_to_question_attempt(self, row) -> QuestionAttempt:
        """Convert database row to QuestionAttempt model."""
        return QuestionAttempt(
            attempt_id=row['attempt_id'],
            question_id=row['question_id'],
            user_id=row['user_id'],
            user_answer=row['user_answer'] if isinstance(row['user_answer'], (dict, list)) else json.loads(row['user_answer']),
            is_correct=row['is_correct'],
            time_spent_seconds=row['time_spent_seconds'],
            attempted_at=row['attempted_at']
        )
