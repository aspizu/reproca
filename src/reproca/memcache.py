from bmemcached import Client


class Memcache(Client):
    def rate_limit(self, accessor: str, resource: str, rate: int) -> bool:
        """Rate limit an accessor for a resource.

        Returns True if the accessor is NOT allowed to access the resource.

        Args:
        ----
            accessor: The accessor to rate limit.
            resource: The resource to rate limit.
            rate: The rate limit in seconds.

        """
        lock = self.get(f"accessor={accessor};resource={resource}")
        if lock:
            return True
        self.set(f"accessor={accessor};resource={resource}", True, time=rate)
        return False
