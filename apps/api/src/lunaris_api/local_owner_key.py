#: The rationing bucket for a caller with no owner — auth off, or a single-user instance.
#:
#: Every per-tenant cap in the API needs a key, and a request without an authenticated owner still
#: has to land in *some* bucket or it would be uncapped. Shared rather than re-declared per throttle
#: because the buckets must agree: two spellings would silently give an unowned caller one allowance
#: per surface, which is exactly the hole a cap is there to close.
LOCAL_OWNER_KEY = "__local__"
