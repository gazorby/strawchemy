from __future__ import annotations

import strawberry

from .types import (
    MilestoneCreate,
    MilestoneType,
    ProjectCreate,
    ProjectType,
    TicketCreate,
    TicketFilter,
    TicketType,
    TicketUpdate,
    strawchemy,
)


@strawberry.type
class Query:
    ticket: TicketType = strawchemy.field()
    tickets: list[TicketType] = strawchemy.field()

    project: ProjectType = strawchemy.field()
    projects: list[ProjectType] = strawchemy.field()

    milestones: list[MilestoneType] = strawchemy.field()


@strawberry.type
class Mutation:
    create_ticket: TicketType = strawchemy.create(TicketCreate)
    create_tickets: list[TicketType] = strawchemy.create(TicketCreate)

    create_project: ProjectType = strawchemy.create(ProjectCreate)
    create_projects: list[ProjectType] = strawchemy.create(ProjectCreate)

    create_milestone: MilestoneType = strawchemy.create(MilestoneCreate)

    update_ticket: TicketType = strawchemy.update_by_ids(TicketUpdate)

    delete_ticket: list[TicketType] = strawchemy.delete(TicketFilter)


schema = strawberry.Schema(query=Query, mutation=Mutation)
