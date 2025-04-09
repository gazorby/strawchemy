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
    create_ticket: TicketType = strawchemy.create_mutation(TicketCreate)
    create_tickets: list[TicketType] = strawchemy.create_mutation(TicketCreate)

    create_project: ProjectType = strawchemy.create_mutation(ProjectCreate)
    create_projects: list[ProjectType] = strawchemy.create_mutation(ProjectCreate)

    create_milestone: MilestoneType = strawchemy.create_mutation(MilestoneCreate)

    update_ticket: TicketType = strawchemy.update_mutation(TicketUpdate)

    delete_ticket: list[TicketType] = strawchemy.delete_mutation(TicketFilter)


schema = strawberry.Schema(query=Query, mutation=Mutation)
