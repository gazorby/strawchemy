from __future__ import annotations

import strawberry

from .types import MilestoneInput, MilestoneType, ProjectInput, ProjectType, TicketInput, TicketType, strawchemy


@strawberry.type
class Query:
    ticket: TicketType = strawchemy.field()
    tickets: list[TicketType] = strawchemy.field()

    project: ProjectType = strawchemy.field()
    projects: list[ProjectType] = strawchemy.field()

    milestones: list[MilestoneType] = strawchemy.field()


@strawberry.type
class Mutation:
    create_ticket: TicketType = strawchemy.create_mutation(TicketInput)
    create_tickets: list[TicketType] = strawchemy.create_mutation(TicketInput)

    create_project: ProjectType = strawchemy.create_mutation(ProjectInput)
    create_projects: list[ProjectType] = strawchemy.create_mutation(ProjectInput)

    create_milestone: MilestoneType = strawchemy.create_mutation(MilestoneInput)


schema = strawberry.Schema(query=Query, mutation=Mutation)
