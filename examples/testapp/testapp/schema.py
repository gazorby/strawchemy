from __future__ import annotations

from strawchemy import ValidationErrorType  # noqa: TC002

import strawberry

from .types import (
    MilestoneCreate,
    MilestoneType,
    ProjectCreate,
    ProjectType,
    TicketCreate,
    TicketCreateValidation,
    TicketFilter,
    TicketPartial,
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
    create_ticket: TicketType | ValidationErrorType = strawchemy.create(TicketCreate, validation=TicketCreateValidation)
    create_tickets: list[TicketType] = strawchemy.create(TicketCreate)

    create_project: ProjectType = strawchemy.create(ProjectCreate)
    create_projects: list[ProjectType] = strawchemy.create(ProjectCreate)

    create_milestone: MilestoneType = strawchemy.create(MilestoneCreate)

    update_tickets_by_ids: TicketType = strawchemy.update_by_ids(TicketUpdate)
    update_tickets: list[TicketType] = strawchemy.update(TicketPartial, TicketFilter)

    delete_ticket: list[TicketType] = strawchemy.delete(TicketFilter)


schema = strawberry.Schema(query=Query, mutation=Mutation)
