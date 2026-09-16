"""
Swiggy Partner Portal GraphQL client (vhc-composer.swiggy.com).
Uses access_token auth captured from Playwright — isolated from Zomato.
"""

from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx

VHC_COMPOSER_BASE = "https://vhc-composer.swiggy.com/query"

BUSINESS_METRICS_QUERY = """
  query businessMetricsDetailsV3($rids: [Int64!]!, $fromDate: Int64!, $toDate: Int64!) {
    businessMetricsDetailsV3(
      input: {
        rids: $rids
        period: CUSTOM
        fromDate: $fromDate
        toDate: $toDate
        metricsType: LAGGED_METRICS
        metricIds: [SALES_V2, CONVERSION_FUNNEL, OPERATIONS_V2]
        manageeIds: [""]
      }
    ) {
      title
      subTitleV2
      businessMetricsDetails {
        id
        title
        metrics {
          id
          cardTitle
          subMetrics {
            cardMetrics {
              id
              label
              value
            }
          }
          current {
            metrics {
              label
              value
              percent
            }
          }
        }
      }
    }
  }
"""

PAST_PAYOUTS_QUERY = """
  query getFinanceRestaurantPastPayouts($restaurantId: Int64!, $fromDate: String!, $toDate: String!) {
    getFinanceRestaurantPastPayouts(input: {
      restaurantId: $restaurantId
      fromDate: $fromDate
      toDate: $toDate
      offset: 0
      limit: 20
    }) {
      payouts {
        payoutId
        netPayout
        week {
          startDate
          endDate
        }
        payoutStatus {
          state
          message
        }
      }
    }
  }
"""

PAYOUT_DETAILS_QUERY = """
  query getRestaurantPayoutDetailsV3(
    $restaurantIds: [Int64!]!
    $payoutId: Int64
    $from: Int64
    $to: Int64
  ) {
    getRestaurantPayoutDetailsV3(
      getRestaurantPayoutDetailsV3Input: {
        restaurantIds: $restaurantIds
        payoutId: $payoutId
        panId: null
        from: $from
        to: $to
      }
    ) {
      data {
        restaurantId
        payoutId
        orderCount
        netPayout
        week {
          startDate
          endDate
        }
        payoutSummary {
          header
          amount
          subHeaders {
            text
            amount
          }
        }
      }
    }
  }
"""

OWNER_OUTLETS_QUERY = """
  query getOwnerFinanceDetailsV2($restaurantIds: [Int64!]!) {
    getOwnerFinanceDetailsV2(restaurantIds: $restaurantIds) {
      outlets {
        id
      }
    }
  }
"""


class SwiggyGraphQLClient:
    """Direct GraphQL client for Swiggy Partner portal internal APIs."""

    DEFAULT_HEADERS = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://partner.swiggy.com",
        "Referer": "https://partner.swiggy.com/food/business-metrics",
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or ""
        self._client: Optional[httpx.Client] = None

    def has_session(self) -> bool:
        return bool(self.access_token)

    def set_access_token(self, token: str) -> None:
        self.access_token = token or ""
        if self._client:
            self._client.close()
            self._client = None

    def _headers(self) -> Dict[str, str]:
        headers = dict(self.DEFAULT_HEADERS)
        if self.access_token:
            headers["access_token"] = self.access_token
        return headers

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(headers=self._headers(), timeout=45.0, follow_redirects=True)
        return self._client

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    @staticmethod
    def _date_to_epoch_ms(dt: datetime, end_of_day: bool = False) -> int:
        if end_of_day:
            dt = datetime.combine(dt.date(), time(23, 59, 59))
        return int(dt.timestamp() * 1000)

    @staticmethod
    def _date_to_epoch_sec(dt: datetime, end_of_day: bool = False) -> int:
        if end_of_day:
            dt = datetime.combine(dt.date(), time(23, 59, 59))
        return int(dt.timestamp())

    def _post(self, operation: str, query: str, variables: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.has_session():
            print("[Swiggy GraphQL] No access_token — cannot call API.")
            return None
        url = f"{VHC_COMPOSER_BASE}?query={operation}"
        try:
            resp = self._get_client().post(url, json={"query": query, "variables": variables})
            if resp.status_code != 200:
                print(f"[Swiggy GraphQL] {operation} failed: HTTP {resp.status_code}")
                return None
            data = resp.json()
            if data.get("errors"):
                print(f"[Swiggy GraphQL] {operation} GraphQL errors: {data['errors'][:1]}")
                return None
            print(f"[Swiggy GraphQL] {operation} OK")
            return data
        except Exception as e:
            print(f"[Swiggy GraphQL] {operation} error: {e}")
            return None

    def fetch_business_metrics(
        self,
        outlet_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[Dict[str, Any]]:
        variables = {
            "rids": [int(outlet_id)],
            "fromDate": self._date_to_epoch_ms(start_date),
            "toDate": self._date_to_epoch_ms(end_date, end_of_day=True),
        }
        return self._post("businessMetricsDetailsV3", BUSINESS_METRICS_QUERY, variables)

    def fetch_past_payouts(
        self,
        outlet_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[Dict[str, Any]]:
        search_start = (start_date - timedelta(days=90)).strftime("%Y-%m-%d")
        variables = {
            "restaurantId": int(outlet_id),
            "fromDate": search_start,
            "toDate": datetime.now().strftime("%Y-%m-%d"),
        }
        return self._post("getFinanceRestaurantPastPayouts", PAST_PAYOUTS_QUERY, variables)

    @staticmethod
    def find_matching_payout(
        past_payouts_response: Dict[str, Any],
        target_start: datetime,
        target_end: datetime,
    ) -> Optional[Dict[str, Any]]:
        payouts = (
            past_payouts_response.get("data", {})
            .get("getFinanceRestaurantPastPayouts", {})
            .get("payouts", [])
        )
        if not payouts:
            return None

        t_start = SwiggyGraphQLClient._date_to_epoch_sec(target_start)
        t_end = SwiggyGraphQLClient._date_to_epoch_sec(target_end, end_of_day=True)

        best = None
        best_score = -1.0
        for p in payouts:
            week = p.get("week") or {}
            w_start = week.get("startDate")
            w_end = week.get("endDate")
            if not w_start or not w_end:
                continue
            overlap_start = max(t_start, w_start)
            overlap_end = min(t_end, w_end)
            overlap = max(0, overlap_end - overlap_start)
            if overlap > best_score:
                best_score = overlap
                best = p
        return best

    def fetch_payout_details(
        self,
        outlet_id: str,
        payout_id: int,
        week_start_sec: int,
        week_end_sec: int,
    ) -> Optional[Dict[str, Any]]:
        variables = {
            "restaurantIds": [int(outlet_id)],
            "payoutId": int(payout_id),
            "from": week_start_sec * 1000,
            "to": week_end_sec * 1000,
        }
        return self._post("getRestaurantPayoutDetailsV3", PAYOUT_DETAILS_QUERY, variables)

    def fetch_payout_for_date_range(
        self,
        outlet_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[Dict[str, Any]]:
        past = self.fetch_past_payouts(outlet_id, start_date, end_date)
        if not past:
            return None
        match = self.find_matching_payout(past, start_date, end_date)
        if not match:
            print(f"[Swiggy GraphQL] No matching payout cycle for {start_date.date()} - {end_date.date()}")
            return None
        week = match.get("week") or {}
        payout_id = match.get("payoutId")
        if not payout_id:
            return None
        print(f"[Swiggy GraphQL] Matched payoutId={payout_id} for target week")
        return self.fetch_payout_details(
            outlet_id,
            int(payout_id),
            int(week.get("startDate", 0)),
            int(week.get("endDate", 0)),
        )

    @staticmethod
    def _extract_outlet_ids_from_owner_finance(block: Any) -> List[int]:
        """getOwnerFinanceDetailsV2 returns a list of PAN groups, each with nested outlets."""
        outlet_ids: List[int] = []
        if isinstance(block, list):
            for pan_group in block:
                if not isinstance(pan_group, dict):
                    continue
                for outlet in pan_group.get("outlets") or []:
                    if isinstance(outlet, dict) and outlet.get("id") is not None:
                        outlet_ids.append(int(outlet["id"]))
        elif isinstance(block, dict):
            for outlet in block.get("outlets") or []:
                if isinstance(outlet, dict) and outlet.get("id") is not None:
                    outlet_ids.append(int(outlet["id"]))
        return sorted(set(outlet_ids))

    def list_accessible_outlet_ids(self, seed_outlet_id: str) -> List[int]:
        """Returns outlet IDs accessible under the logged-in partner account."""
        resp = self._post(
            "getOwnerFinanceDetailsV2",
            OWNER_OUTLETS_QUERY,
            {"restaurantIds": [int(seed_outlet_id)]},
        )
        if not resp:
            return []
        block = resp.get("data", {}).get("getOwnerFinanceDetailsV2")
        return self._extract_outlet_ids_from_owner_finance(block)
