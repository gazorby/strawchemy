from __future__ import annotations

from typing import TYPE_CHECKING

import strawberry
from strawchemy.validation.pydantic import PydanticValidation
from testapp.types import (
    CustomerCreate,
    CustomerType,
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
    TicketUpsertConflictFields,
    TicketUpsertFields,
    strawchemy,
)

if TYPE_CHECKING:
    from strawchemy import ValidationErrorType


@strawberry.type
class Query:
    ticket: TicketType = strawchemy.field()
    tickets: list[TicketType] = strawchemy.field()

    project: ProjectType = strawchemy.field()
    projects: list[ProjectType] = strawchemy.field()

    milestones: list[MilestoneType] = strawchemy.field()


@strawberry.type
class Mutation:
    create_ticket: TicketType | ValidationErrorType = strawchemy.create(
        TicketCreate, validation=PydanticValidation(TicketCreateValidation)
    )
    create_tickets: list[TicketType] = strawchemy.create(TicketCreate)
    upsert_ticket: TicketType = strawchemy.upsert(
        TicketCreate, update_fields=TicketUpsertFields, conflict_fields=TicketUpsertConflictFields
    )

    create_project: ProjectType = strawchemy.create(ProjectCreate)
    create_projects: list[ProjectType] = strawchemy.create(ProjectCreate)

    create_milestone: MilestoneType = strawchemy.create(MilestoneCreate)

    update_tickets_by_ids: TicketType = strawchemy.update_by_ids(TicketUpdate)
    update_tickets: list[TicketType] = strawchemy.update(TicketPartial, TicketFilter)

    delete_ticket: list[TicketType] = strawchemy.delete(TicketFilter)

    create_customer: CustomerType = strawchemy.create(CustomerCreate)


schema = strawberry.Schema(query=Query, mutation=Mutation)
