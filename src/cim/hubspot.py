"""HubSpot CRM API client for Cast Iron Media prospect enrichment.

Wraps the HubSpot v3/v4 CRM REST API using httpx. All requests use
Bearer token authentication. The client manages a single httpx.Client
instance — call close() when done, or use it as a context manager.

Supported objects: companies, contacts, notes, tasks, properties.
Association uses the v4 associations endpoint which supports custom
association types between CRM object types.
"""

import time

import httpx


class HubSpotClient:
    """Synchronous HubSpot CRM client.

    Provides methods for creating and updating CRM objects, searching
    companies, managing custom property groups/definitions, and linking
    objects via associations.

    Args:
        api_key:  HubSpot Private App access token (Bearer auth).
        base_url: API root, defaults to https://api.hubapi.com. Override
                  to point at a sandbox portal during testing.
    """

    def __init__(self, api_key: str, base_url: str = "https://api.hubapi.com") -> None:
        # Store base_url for building endpoint paths in each method
        self._base_url = base_url.rstrip("/")

        # Single shared httpx.Client with Bearer token injected on every request.
        # Reusing a single client enables HTTP/1.1 keep-alive and connection pooling,
        # which matters when making many sequential API calls during enrichment runs.
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _now_ms(self) -> str:
        """Return the current UTC time as a millisecond epoch string.

        HubSpot stores timestamps (hs_timestamp, hs_task_due_date, etc.)
        as millisecond-precision epoch integers serialised as strings.
        """
        return str(int(time.time() * 1000))

    def _associate(
        self,
        from_type: str,
        from_id: str | int,
        to_type: str,
        to_id: str | int,
    ) -> None:
        """Create a default association between two CRM objects (v4 API).

        Uses the v4 associations endpoint which requires an array of
        associationSpec objects. The default association type between any
        two built-in object types can be referenced with category
        HUBSPOT_DEFINED and typeId 1 (generic "primary" relationship).

        Args:
            from_type: Source object type slug (e.g. "notes", "tasks").
            from_id:   Source object's HubSpot numeric ID.
            to_type:   Target object type slug (e.g. "companies").
            to_id:     Target object's HubSpot numeric ID.

        Raises:
            httpx.HTTPStatusError: If HubSpot returns a 4xx/5xx response.
        """
        url = (
            f"{self._base_url}/crm/v4/objects/{from_type}/{from_id}"
            f"/associations/{to_type}/{to_id}"
        )
        # v4 associations require an array of associationSpec objects.
        # typeId=1 is the default "primary" relationship defined by HubSpot
        # between most standard object pairs.
        payload = [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 1}]
        resp = self._client.put(url, json=payload)
        resp.raise_for_status()

    # ------------------------------------------------------------------
    # Company methods
    # ------------------------------------------------------------------

    def create_company(self, properties: dict) -> dict:
        """Create a new company record in HubSpot CRM.

        Args:
            properties: Dict of HubSpot company property names to values.
                        e.g. {"name": "Acme Corp", "domain": "acme.com"}

        Returns:
            The full HubSpot response JSON (includes "id" key).

        Raises:
            httpx.HTTPStatusError: On API error.
        """
        url = f"{self._base_url}/crm/v3/objects/companies"
        resp = self._client.post(url, json={"properties": properties})
        resp.raise_for_status()
        return resp.json()

    def update_company(self, company_id: str | int, properties: dict) -> dict:
        """Update an existing company record by ID.

        Uses PATCH semantics — only supplied properties are modified;
        omitted properties are left unchanged.

        Args:
            company_id: HubSpot numeric company ID.
            properties: Dict of property names to new values.

        Returns:
            The updated company object from HubSpot.

        Raises:
            httpx.HTTPStatusError: On API error (404 if not found).
        """
        url = f"{self._base_url}/crm/v3/objects/companies/{company_id}"
        resp = self._client.patch(url, json={"properties": properties})
        resp.raise_for_status()
        return resp.json()

    def get_company(
        self,
        company_id: str | int,
        properties: list[str] | None = None,
    ) -> dict:
        """Fetch a single company record by ID.

        Args:
            company_id: HubSpot numeric company ID.
            properties: Optional list of property names to include in the
                        response. If None, HubSpot returns default fields.

        Returns:
            Company object dict from HubSpot.

        Raises:
            httpx.HTTPStatusError: On API error (404 if not found).
        """
        url = f"{self._base_url}/crm/v3/objects/companies/{company_id}"
        params: dict = {}
        if properties:
            # HubSpot accepts a comma-separated "properties" query param
            params["properties"] = ",".join(properties)
        resp = self._client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    def search_companies(self, query: str) -> list[dict]:
        """Search companies by name using CONTAINS_TOKEN filter.

        CONTAINS_TOKEN is the correct operator for partial name matches
        in HubSpot search — it tokenises the value and matches any company
        whose name contains that token, case-insensitively.

        Args:
            query: Search string to match against company names.

        Returns:
            List of company result dicts from the "results" key.

        Raises:
            httpx.HTTPStatusError: On API error.
        """
        url = f"{self._base_url}/crm/v3/objects/companies/search"
        payload = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "name",
                            "operator": "CONTAINS_TOKEN",
                            "value": query,
                        }
                    ]
                }
            ]
        }
        resp = self._client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json().get("results", [])

    # ------------------------------------------------------------------
    # Contact methods
    # ------------------------------------------------------------------

    def create_contact(self, properties: dict) -> dict:
        """Create a new contact record in HubSpot CRM.

        Args:
            properties: Dict of HubSpot contact property names to values.
                        e.g. {"firstname": "Jane", "email": "j@acme.com"}

        Returns:
            The full HubSpot response JSON (includes "id" key).

        Raises:
            httpx.HTTPStatusError: On API error (409 if email exists).
        """
        url = f"{self._base_url}/crm/v3/objects/contacts"
        resp = self._client.post(url, json={"properties": properties})
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Note methods
    # ------------------------------------------------------------------

    def create_note(self, body: str, company_id: str | int | None = None) -> dict:
        """Create a CRM note, optionally associating it with a company.

        Notes require hs_timestamp (epoch ms) and hs_note_body. After
        creation, if company_id is provided, an association is created
        from the note to the company using the v4 associations API.

        Args:
            body:       Plaintext or HTML content of the note.
            company_id: If provided, associate the new note with this
                        HubSpot company ID.

        Returns:
            The created note object from HubSpot (includes "id").

        Raises:
            httpx.HTTPStatusError: On API error.
        """
        url = f"{self._base_url}/crm/v3/objects/notes"
        payload = {
            "properties": {
                "hs_timestamp": self._now_ms(),
                "hs_note_body": body,
            }
        }
        resp = self._client.post(url, json=payload)
        resp.raise_for_status()
        note = resp.json()

        # Associate the note with the company if one was provided.
        # This surfaces the note in the company's activity timeline.
        if company_id is not None:
            self._associate("notes", note["id"], "companies", company_id)

        return note

    # ------------------------------------------------------------------
    # Task methods
    # ------------------------------------------------------------------

    def create_task(
        self,
        subject: str,
        body: str = "",
        company_id: str | int | None = None,
    ) -> dict:
        """Create a CRM task, optionally associating it with a company.

        Tasks are created with HIGH priority and NOT_STARTED status by
        default — these are the standard defaults for sales follow-up
        tasks created by the enrichment pipeline. hs_timestamp marks
        creation time; hs_task_due_date is left unset (caller can update).

        Args:
            subject:    Task subject line (maps to hs_task_subject).
            body:       Optional task description / notes body.
            company_id: If provided, associate the new task with this
                        HubSpot company ID.

        Returns:
            The created task object from HubSpot (includes "id").

        Raises:
            httpx.HTTPStatusError: On API error.
        """
        url = f"{self._base_url}/crm/v3/objects/tasks"
        payload = {
            "properties": {
                "hs_timestamp": self._now_ms(),
                "hs_task_subject": subject,
                "hs_task_body": body,
                # NOT_STARTED is the required initial status for new tasks
                "hs_task_status": "NOT_STARTED",
                # HIGH priority flags this task for immediate attention
                "hs_task_priority": "HIGH",
            }
        }
        resp = self._client.post(url, json=payload)
        resp.raise_for_status()
        task = resp.json()

        # Associate the task with the company so it appears in their record
        if company_id is not None:
            self._associate("tasks", task["id"], "companies", company_id)

        return task

    # ------------------------------------------------------------------
    # Property management methods
    # ------------------------------------------------------------------

    def create_property_group(
        self,
        object_type: str,
        name: str,
        label: str,
    ) -> dict:
        """Create a custom property group for a CRM object type.

        Property groups organise custom properties into labelled sections
        in the HubSpot UI. A 409 Conflict response means the group already
        exists, which is treated as success (idempotent operation).

        Args:
            object_type: CRM object type slug (e.g. "companies", "contacts").
            name:        Internal machine-readable group name (snake_case).
            label:       Human-readable display label shown in HubSpot UI.

        Returns:
            The created (or existing) property group dict from HubSpot,
            or an empty dict if the group already existed (409 case).

        Raises:
            httpx.HTTPStatusError: On API errors other than 409.
        """
        url = f"{self._base_url}/crm/v3/properties/{object_type}/groups"
        payload = {"name": name, "label": label}
        resp = self._client.post(url, json=payload)

        # 409 Conflict means the group already exists — treat as idempotent success
        # so this method is safe to call on repeated runs without manual cleanup.
        if resp.status_code == 409:
            return {}

        resp.raise_for_status()
        return resp.json()

    def create_properties(
        self,
        object_type: str,
        definitions: list[dict],
    ) -> dict:
        """Batch-create custom properties for a CRM object type.

        Uses the batch create endpoint to minimise API round-trips when
        setting up multiple custom fields. Each definition dict must include
        at minimum: name, label, type, fieldType, groupName.

        Args:
            object_type:  CRM object type slug (e.g. "companies").
            definitions:  List of property definition dicts.

        Returns:
            The HubSpot batch create response (contains "results" list).

        Raises:
            httpx.HTTPStatusError: On API error.
        """
        url = f"{self._base_url}/crm/v3/properties/{object_type}/batch/create"
        resp = self._client.post(url, json={"inputs": definitions})
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying httpx client and release connections.

        Call this when the HubSpotClient is no longer needed. Failure to
        close may leave sockets open until garbage collection.
        """
        self._client.close()

    def __enter__(self) -> "HubSpotClient":
        """Support use as a context manager: `with HubSpotClient(...) as hs:`."""
        return self

    def __exit__(self, *_: object) -> None:
        """Ensure close() is called when leaving a with-block."""
        self.close()
