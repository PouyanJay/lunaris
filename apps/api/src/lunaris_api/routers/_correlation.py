from uuid import uuid4

from fastapi import Response
from lunaris_runtime.logging import bind_request_id


def bind_correlation(response: Response) -> str:
    """Bind a fresh correlation id + surface it in ``X-Request-Id``, returning the id.

    Shared by the admin routers so a privileged action (an account change, a prod-operations read
    or start/stop) is traceable across the logs from one id. Returning the id lets the caller also
    stamp it onto an audit log line.
    """
    request_id = uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id
    return request_id
