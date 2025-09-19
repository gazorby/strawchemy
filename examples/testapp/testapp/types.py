from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator
from strawchemy import Strawchemy, StrawchemyAsyncRepository, StrawchemyConfig

from .models import Customer, Milestone, Project, Ticket

strawchemy = Strawchemy(StrawchemyConfig("sqlite", repository_type=StrawchemyAsyncRepository))

# Ticket


@strawchemy.order(Ticket, include="all")
class TicketOrder: ...


@strawchemy.filter(Ticket, include="all")
class TicketFilter: ...


@strawchemy.type(Ticket, include="all", filter_input=TicketFilter, order_by=TicketOrder, override=True)
class TicketType: ...


@strawchemy.upsert_update_fields(Ticket, include="all")
class TicketUpsertFields: ...


@strawchemy.upsert_conflict_fields(Ticket, include="all")
class TicketUpsertConflictFields: ...


@strawchemy.create_input(Ticket, include="all")
class TicketCreate: ...


@strawchemy.pk_update_input(Ticket, include="all")
class TicketUpdate: ...


@strawchemy.filter_update_input(Ticket, include="all")
class TicketPartial: ...


# Project


@strawchemy.order(Project, include="all")
class ProjectOrder: ...


@strawchemy.filter(Project, include="all")
class ProjectFilter: ...


@strawchemy.type(Project, include="all", filter_input=ProjectFilter, order_by=ProjectOrder, override=True)
class ProjectType: ...


@strawchemy.create_input(Project, include={"name"}, scope="schema")
class ProjectCreate: ...


# Milestone


@strawchemy.type(Milestone, include="all", override=True)
class MilestoneType: ...


@strawchemy.create_input(Milestone, include="all", override=True)
class MilestoneCreate: ...


# Customer


@strawchemy.type(Customer, include="all", override=True)
class CustomerType: ...


@strawchemy.create_input(Customer, include="all", override=True)
class CustomerCreate: ...


# Validation


def _check_ticket_name(value: str) -> str:
    prefixes = ("bug:", "feature:", "perf:", "build:")
    if not any(value.startswith(prefix) for prefix in prefixes):
        msg = f"Ticket name must start with one of: {', '.join(prefixes)}"
        raise ValueError(msg)
    return value


@strawchemy.pydantic.create(Ticket, include="all")
class TicketCreateValidation:
    name: Annotated[str, AfterValidator(_check_ticket_name)]
