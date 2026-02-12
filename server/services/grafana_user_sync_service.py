# grafana_user_sync_service.py — REMOVED
# Grafana user-sync functionality has been deprecated and removed from the codebase.
# Keeping this placeholder prevents accidental imports; any attempt to use it will
# raise an explicit error so callers can be refactored.

raise RuntimeError("GrafanaUserSyncService removed — user sync is deprecated")


    @with_retry()
    @with_timeout()
    async def update_grafana_user(
        self,
        grafana_user_id: int,
        *,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        login: Optional[str] = None,
    ) -> bool:
        """Update basic Grafana user profile fields."""
        payload: Dict[str, Any] = {}
        if email:
            payload["email"] = email
        if full_name:
            payload["name"] = full_name
        if login:
            payload["login"] = login
        if not payload:
            return True
        try:
            resp = await self._client.put(
                f"{self.grafana_url}/api/admin/users/{grafana_user_id}",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error updating Grafana user %s: %s", grafana_user_id, e)
            return False

    @with_retry()
    @with_timeout()
    async def update_grafana_user_password(
        self, grafana_user_id: int, new_password: str
    ) -> bool:
        """Change Grafana user password via admin API."""
        try:
            resp = await self._client.put(
                f"{self.grafana_url}/api/admin/users/{grafana_user_id}/password",
                json={"password": new_password},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error updating Grafana password for user %s: %s", grafana_user_id, e)
            return False

    @with_retry()
    @with_timeout()
    async def delete_grafana_user(self, grafana_user_id: int) -> bool:
        """Delete a Grafana user."""
        try:
            resp = await self._client.delete(
                f"{self.grafana_url}/api/admin/users/{grafana_user_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            logger.info("Deleted Grafana user id=%s", grafana_user_id)
            return True
        except httpx.HTTPError as e:
            logger.error("Error deleting Grafana user %s: %s", grafana_user_id, e)
            return False

    async def _set_user_org_role(self, grafana_user_id: int, role: str) -> bool:
        """Set the user's role in the default org."""
        try:
            resp = await self._client.patch(
                f"{self.grafana_url}/api/org/users/{grafana_user_id}",
                json={"role": role},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error setting role for Grafana user %s: %s", grafana_user_id, e)
            return False

    @with_retry()
    @with_timeout()
    async def sync_user_role(self, grafana_user_id: int, app_role: str) -> bool:
        """Sync the app role to Grafana org role."""
        grafana_role = self.ROLE_MAP.get(app_role, "Viewer")
        return await self._set_user_org_role(grafana_user_id, grafana_role)

    # ------------------------------------------------------------------
    # Grafana Team management (maps to our groups)
    # ------------------------------------------------------------------

    @with_retry()
    @with_timeout()
    async def create_team(self, name: str, email: str = "") -> Optional[Dict[str, Any]]:
        """Create a Grafana team."""
        try:
            resp = await self._client.post(
                f"{self.grafana_url}/api/teams",
                json={"name": name, "email": email},
                headers=self._headers(),
            )
            if resp.status_code == 409:
                # Team already exists
                return await self.get_team_by_name(name)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Error creating Grafana team '%s': %s", name, e)
            return None

    @with_retry()
    @with_timeout()
    async def get_team_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find a Grafana team by name."""
        try:
            resp = await self._client.get(
                f"{self.grafana_url}/api/teams/search",
                params={"name": name},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            teams = data.get("teams", [])
            for t in teams:
                if t.get("name") == name:
                    return t
            return None
        except httpx.HTTPError as e:
            logger.error("Error searching Grafana team '%s': %s", name, e)
            return None

    @with_retry()
    @with_timeout()
    async def add_user_to_team(self, team_id: int, grafana_user_id: int) -> bool:
        """Add a Grafana user to a Grafana team."""
        try:
            resp = await self._client.post(
                f"{self.grafana_url}/api/teams/{team_id}/members",
                json={"userId": grafana_user_id},
                headers=self._headers(),
            )
            if resp.status_code == 400:
                # Already a member
                return True
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error adding user %s to team %s: %s", grafana_user_id, team_id, e)
            return False

    @with_retry()
    @with_timeout()
    async def remove_user_from_team(self, team_id: int, grafana_user_id: int) -> bool:
        """Remove a Grafana user from a Grafana team."""
        try:
            resp = await self._client.delete(
                f"{self.grafana_url}/api/teams/{team_id}/members/{grafana_user_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error removing user %s from team %s: %s", grafana_user_id, team_id, e)
            return False

    @with_retry()
    @with_timeout()
    async def delete_team(self, team_id: int) -> bool:
        """Delete a Grafana team."""
        try:
            resp = await self._client.delete(
                f"{self.grafana_url}/api/teams/{team_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error deleting Grafana team %s: %s", team_id, e)
            return False

    # ------------------------------------------------------------------
    # Dashboard / folder permissions in Grafana
    # ------------------------------------------------------------------

    @with_retry()
    @with_timeout()
    async def set_dashboard_permissions(
        self,
        dashboard_uid: str,
        permissions: List[Dict[str, Any]],
    ) -> bool:
        """Set Grafana-native permissions on a dashboard.

        ``permissions`` is a list of dicts, each with:
            - ``role``, ``userId``, or ``teamId``
            - ``permission``: 1=View, 2=Edit, 4=Admin
        """
        try:
            # First get dashboard id from uid
            resp = await self._client.get(
                f"{self.grafana_url}/api/dashboards/uid/{dashboard_uid}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            dash_data = resp.json()
            dash_id = dash_data.get("dashboard", {}).get("id")
            if not dash_id:
                return False

            resp = await self._client.post(
                f"{self.grafana_url}/api/dashboards/id/{dash_id}/permissions",
                json={"items": permissions},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error setting dashboard permissions for %s: %s", dashboard_uid, e)
            return False

    @with_retry()
    @with_timeout()
    async def set_folder_permissions(
        self,
        folder_uid: str,
        permissions: List[Dict[str, Any]],
    ) -> bool:
        """Set Grafana-native permissions on a folder."""
        try:
            resp = await self._client.post(
                f"{self.grafana_url}/api/folders/{folder_uid}/permissions",
                json={"items": permissions},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error setting folder permissions for %s: %s", folder_uid, e)
            return False

    # ------------------------------------------------------------------
    # Service account & API token management
    # ------------------------------------------------------------------

    @with_retry()
    @with_timeout()
    async def create_service_account(
        self, name: str, role: str = "Viewer"
    ) -> Optional[Dict[str, Any]]:
        """Create a Grafana service account for API token generation."""
        try:
            resp = await self._client.post(
                f"{self.grafana_url}/api/serviceaccounts",
                json={"name": name, "role": role, "isDisabled": False},
                headers=self._headers(),
            )
            if resp.status_code == 409:
                logger.info("Service account '%s' already exists", name)
                return await self._find_service_account(name)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Error creating service account '%s': %s", name, e)
            return None

    async def _find_service_account(self, name: str) -> Optional[Dict[str, Any]]:
        """Find a service account by name."""
        try:
            resp = await self._client.get(
                f"{self.grafana_url}/api/serviceaccounts/search",
                params={"query": name},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            for sa in data.get("serviceAccounts", []):
                if sa.get("name") == name:
                    return sa
            return None
        except httpx.HTTPError:
            return None

    @with_retry()
    @with_timeout()
    async def create_service_account_token(
        self, sa_id: int, token_name: str
    ) -> Optional[str]:
        """Create API token for a service account. Returns the token string."""
        try:
            resp = await self._client.post(
                f"{self.grafana_url}/api/serviceaccounts/{sa_id}/tokens",
                json={"name": token_name},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("key")
        except httpx.HTTPError as e:
            logger.error("Error creating SA token for %s: %s", sa_id, e)
            return None

    @with_retry()
    @with_timeout()
    async def delete_service_account(self, sa_id: int) -> bool:
        """Delete a Grafana service account."""
        try:
            resp = await self._client.delete(
                f"{self.grafana_url}/api/serviceaccounts/{sa_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error deleting service account %s: %s", sa_id, e)
            return False

    # ------------------------------------------------------------------
    # Convenience: full user lifecycle sync
    # ------------------------------------------------------------------

    async def sync_user_create(
        self,
        username: str,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        role: str = "user",
    ) -> Optional[int]:
        """Create Grafana user and return grafana_user_id, or None on error."""
        result = await self.create_grafana_user(
            username=username,
            email=email,
            password=password,
            full_name=full_name,
            role=role,
        )
        if result:
            return result.get("id")
        return None

    async def sync_user_delete(self, grafana_user_id: int) -> bool:
        """Remove user from Grafana entirely."""
        if not grafana_user_id:
            return True
        return await self.delete_grafana_user(grafana_user_id)

    async def sync_group_to_team(self, group_name: str) -> Optional[int]:
        """Ensure a Grafana team exists for the group. Returns team_id."""
        result = await self.create_team(group_name)
        if result:
            return result.get("teamId") or result.get("id")
        return None
