from coworker.server.identity import Principal
from coworker.server.principal_managers import PrincipalManagerRegistry


class _Manager:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id


def test_principal_manager_registry_binds_and_reuses_each_user() -> None:
    created: list[str] = []

    def factory(principal: Principal) -> _Manager:
        created.append(principal.user_id)
        return _Manager(principal.user_id)

    registry = PrincipalManagerRegistry(_Manager("default"), factory)

    assert registry.user_id == "default"
    alice_token = registry.activate(Principal("alice", "test"))
    assert registry.user_id == "alice"
    registry.deactivate(alice_token)
    assert registry.user_id == "default"

    alice_again = registry.activate(Principal("alice", "test"))
    assert registry.user_id == "alice"
    registry.deactivate(alice_again)

    bob_token = registry.activate(Principal("bob", "test"))
    assert registry.user_id == "bob"
    registry.deactivate(bob_token)

    assert created == ["alice", "bob"]
