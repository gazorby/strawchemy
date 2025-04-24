from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator
from strawchemy import Strawchemy, StrawchemyAsyncRepository
from strawchemy.config import StrawchemyConfig

from .models import Milestone, Project, Ticket

strawchemy = Strawchemy(StrawchemyConfig(repository_type=StrawchemyAsyncRepository))

# Filter


@strawchemy.filter(Ticket, include="all")
class TicketFilter: ...


@strawchemy.filter(Project, include="all")
class ProjectFilter: ...


# Order


@strawchemy.order(Ticket, include="all")
class TicketOrder: ...


@strawchemy.order(Project, include="all")
class ProjectOrder: ...


# types


@strawchemy.type(Ticket, include="all", filter_input=TicketFilter, order_by=TicketOrder, override=True)
class TicketType: ...


@strawchemy.type(Project, include="all", filter_input=ProjectFilter, order_by=ProjectOrder, override=True)
class ProjectType: ...


@strawchemy.type(Milestone, include="all", override=True)
class MilestoneType: ...


# Input types


@strawchemy.create_input(Ticket, include="all")
class TicketCreate: ...


@strawchemy.pk_update_input(Ticket, include="all")
class TicketUpdate: ...


@strawchemy.filter_update_input(Ticket, include="all")
class TicketPartial: ...


@strawchemy.create_input(Project, include="all", override=True)
class ProjectCreate: ...


@strawchemy.create_input(Milestone, include="all", override=True)
class MilestoneCreate: ...


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
