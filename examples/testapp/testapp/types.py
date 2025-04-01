from __future__ import annotations

from strawchemy import Strawchemy

from .models import Milestone, Project, Ticket

strawchemy = Strawchemy()

# Filter


@strawchemy.filter_input(Ticket, include="all")
class TicketFilter: ...


@strawchemy.filter_input(Project, include="all")
class ProjectFilter: ...


# Order


@strawchemy.order_by_input(Ticket, include="all")
class TicketOrder: ...


@strawchemy.order_by_input(Project, include="all")
class ProjectOrder: ...


# types


@strawchemy.type(Ticket, include="all", filter_input=TicketFilter, order_by=TicketOrder, override=True)
class TicketType: ...


@strawchemy.type(Project, include="all", filter_input=ProjectFilter, order_by=ProjectOrder, override=True)
class ProjectType: ...


@strawchemy.type(Milestone, include="all", override=True)
class MilestoneType: ...


# Input types


@strawchemy.input(Ticket, "create", include="all")
class TicketInput: ...


@strawchemy.input(Project, "create", include="all", override=True)
class ProjectInput: ...


@strawchemy.input(Milestone, "create", include="all", override=True)
class MilestoneInput: ...
