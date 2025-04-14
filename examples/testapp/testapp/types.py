from __future__ import annotations

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
