from anyio import run

from dataclasses import dataclass
from datetime import timedelta, datetime
from typing import List, Dict
from pprint import pprint
from copy import copy
import calendar
import random

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import text, DateTime, Table, select
from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Integer, Unicode, Interval, UnicodeText
from sqlalchemy.orm import declarative_base, Session, selectinload
from sqlalchemy.orm import relationship

Base = declarative_base()


class Exercise(Base):
    __tablename__ = "exercise"
    id = Column(Integer, primary_key=True)

    name = Column(Unicode(30))  # Short name of the workout
    description = Column(UnicodeText())  # Description of the details of the workout
    rep_description = Column(UnicodeText())  # Description of what counts as 1 rep

    minimum_reps = Column(Integer())
    maximum_reps = Column(Integer())
    minimum_sets = Column(Integer())
    maximum_sets = Column(Integer())

    minimum_timedelta_between = Column(Interval())  # Minimum amount of time to put between each time of this exercise
    maximum_timedelta_between = Column(Interval())  # Maximum amount of time to put between each time of this exercise

    goals = relationship("GoalPeriod", back_populates="exercise", cascade="all, delete-orphan", lazy="selectin")


class GoalPeriod(Base):
    __tablename__ = "goal_period"

    id = Column(Integer, primary_key=True)
    period = Column(Interval())  # The period of time we hope to achieve these within
    reps_per_period = Column(Integer)  # Number of reps we hope to do within a certain period
    sets_per_period = Column(Integer)  # Number of sets we hope to do within a certain period

    exercise_id = Column(Integer(), ForeignKey("exercise.id"))
    exercise = relationship("Exercise", back_populates="goals")


class WorkoutPeriod(Base):
    __tablename__ = "workout_period"
    id = Column(Integer, primary_key=True)

    day_of_week = Column(Integer())
    start = Column(Interval())
    end = Column(Interval())

    __mapper_args__ = {"eager_defaults": True}

    def is_in(self, now):
        d = datetime(now.year, now.month, now.day, tzinfo=now.tzinfo)
        start = d + self.start
        end = d + self.end
        return start <= now <= end


workout_plan_to_exercises_association_table = Table(
    "workout_plan_to_exercises",
    Base.metadata,
    Column("exercise_id", ForeignKey("exercise.id"), primary_key=True),
    Column("workout_plan_id", ForeignKey("workout_plan.id"), primary_key=True)
)

workout_plan_to_workout_periods_association_table = Table(
    "workout_plan_to_workout_periods",
    Base.metadata,
    Column("workout_period_id", ForeignKey("workout_period.id"), primary_key=True),
    Column("workout_plan_id", ForeignKey("workout_plan.id"), primary_key=True)
)


class WorkoutPlan(Base):
    __tablename__ = "workout_plan"
    id = Column(Integer, primary_key=True)

    name = Column(Unicode(30))
    exercises = relationship("Exercise", secondary=workout_plan_to_exercises_association_table, lazy="selectin")
    periods = relationship("WorkoutPeriod", secondary=workout_plan_to_workout_periods_association_table,
                           lazy="selectin")


class Action(Base):
    __tablename__ = "action"
    id = Column(Integer, primary_key=True)

    time = Column(DateTime(timezone=True))
    reps = Column(Integer())
    sets = Column(Integer())
    exercise_id = Column(Integer(), ForeignKey("exercise.id"))
    exercise = relationship("Exercise", uselist=False)


class Workout:
    def __init__(self, workout_plan: WorkoutPlan):
        self.workout_plan = workout_plan
        self.actions = []

    def is_exercise_available(self, now, exercise):
        for action in reversed(self.actions):
            if action.exercise == exercise:
                if (now - action.time) < exercise.minimum_timedelta_between:
                    return False
        return True

    def has_unmet_goals(self, now, exercise):
        for goal in exercise.goals:
            earliest_goal_time = now - goal.period
            running_reps = 0
            running_sets = 0
            for action in self.actions:
                if action.exercise != exercise:
                    continue
                if action.time < earliest_goal_time:
                    continue
                running_reps += action.reps
                running_sets += action.sets
            if running_reps < goal.reps_per_period and running_sets <= goal.sets_per_period:
                return True
        return False

    def been_too_long(self, now, exercise):
        minimum_longest_time = now - exercise.maximum_timedelta_between
        for action in self.actions:
            if action.exercise != exercise:
                continue
            if action.time >= minimum_longest_time:
                return False
        return True

    def _do_exercise_action(self, now, exercise):
        a = Action(exercise=exercise, time=now, reps=0, sets=0)
        a.reps = random.randint(exercise.minimum_reps, exercise.maximum_reps)
        a.sets = random.randint(exercise.minimum_sets, exercise.maximum_sets)
        self.actions.append(a)
        return a

    async def pick_action_for(self, now):
        # Don't do any selecting if outside of the workout hours
        out_of_working_hours = True
        for period in self.workout_plan.periods:
            if period.day_of_week == now.weekday() and period.is_in(now):
                out_of_working_hours = False
        if out_of_working_hours:
            return None
        # Gather all available exercises
        available = [e for e in self.workout_plan.exercises if self.is_exercise_available(now, e)]
        if 0 == len(available):
            return None
        # Pick an unmet exercise first
        unmet = [e for e in available if self.has_unmet_goals(now, e)]
        if 0 != len(unmet):
            random.shuffle(unmet)
            return self._do_exercise_action(now, unmet[0])
        passed_max = [e for e in available if self.been_too_long(now, e)]
        if 0 != len(passed_max):
            random.shuffle(passed_max)
            return self._do_exercise_action(now, passed_max[0])
        # Pick from remaining exercises
        random.shuffle(available)
        return self._do_exercise_action(now, available[0])


def andrew_exercises():
    return [
        Exercise(
            name="squats",
            description="squats",
            rep_description="1 squat",
            minimum_reps=5,
            maximum_reps=10,
            minimum_sets=1,
            maximum_sets=2,
            minimum_timedelta_between=timedelta(hours=16),
            maximum_timedelta_between=timedelta(days=2),
            goals=[GoalPeriod(period=timedelta(weeks=1), reps_per_period=30, sets_per_period=3)]
        ),
        Exercise(
            name="Open books",
            description="Lie on your side and raise one arm away from the other like you're a book being opened",
            rep_description="1 minute of open books on left and right side",
            minimum_reps=1,
            maximum_reps=3,
            minimum_sets=1,
            maximum_sets=1,
            minimum_timedelta_between=timedelta(days=2),
            maximum_timedelta_between=timedelta(days=7),
            goals=[GoalPeriod(period=timedelta(weeks=1), reps_per_period=1, sets_per_period=1)]
        ),
        Exercise(
            name="Stair calf raises",
            description="Stand on the edge of the stairs with your foot just less than half-way on. Drop down for 30 seconds and then do five calf raises",
            rep_description="30 second drop and 5 calf raises",
            minimum_reps=1,
            maximum_reps=5,
            minimum_sets=1,
            maximum_sets=1,
            minimum_timedelta_between=timedelta(days=2),
            maximum_timedelta_between=timedelta(days=7),
            goals=[GoalPeriod(period=timedelta(weeks=1), reps_per_period=1, sets_per_period=1)]
        ),
        Exercise(
            name="Calf book stretch and raise",
            description="Place books a foot or two away from the wall. Stand with your foot half-way on. Lean into wall for 30 seconds then do five calf raises",
            rep_description="30 second drop and 5 calf raises",
            minimum_reps=1,
            maximum_reps=5,
            minimum_sets=1,
            maximum_sets=1,
            minimum_timedelta_between=timedelta(days=2),
            maximum_timedelta_between=timedelta(days=7),
            goals=[GoalPeriod(period=timedelta(weeks=1), reps_per_period=1, sets_per_period=1)]
        ),
        Exercise(
            name="Leg marches",
            description="",
            rep_description="1 march",
            minimum_reps=10,
            maximum_reps=10,
            minimum_sets=1,
            maximum_sets=3,
            minimum_timedelta_between=timedelta(hours=1),
            maximum_timedelta_between=timedelta(hours=2),
            goals=[GoalPeriod(period=timedelta(weeks=1), reps_per_period=30, sets_per_period=3)]
        ),
        Exercise(
            name="Bridges",
            description="",
            rep_description="1 bridge",
            minimum_reps=10,
            maximum_reps=10,
            minimum_sets=1,
            maximum_sets=3,
            minimum_timedelta_between=timedelta(hours=16),
            maximum_timedelta_between=timedelta(days=7),
            goals=[GoalPeriod(period=timedelta(weeks=1), reps_per_period=30, sets_per_period=3)]
        ),
        Exercise(
            name="Clamshells with resistance band",
            description="",
            rep_description="1 clamshell on left and right side",
            minimum_reps=10,
            maximum_reps=10,
            minimum_sets=1,
            maximum_sets=3,
            minimum_timedelta_between=timedelta(hours=16),
            maximum_timedelta_between=timedelta(days=7),
            goals=[GoalPeriod(period=timedelta(weeks=1), reps_per_period=30, sets_per_period=3)]
        ),
        Exercise(
            name="Farmer's carry",
            description="",
            rep_description="1 minute of walking with 25lbs resistance",
            minimum_reps=1,
            maximum_reps=1,
            minimum_sets=2,
            maximum_sets=4,
            minimum_timedelta_between=timedelta(hours=16),
            maximum_timedelta_between=timedelta(days=7),
            goals=[GoalPeriod(period=timedelta(weeks=1), reps_per_period=4, sets_per_period=4)]
        )
    ]


async def andrew_workout_plan(session):
    wp = WorkoutPlan(
        name="Andrew's Workout Plan",
        exercises=andrew_exercises(),
        periods=[
            WorkoutPeriod(day_of_week=calendar.MONDAY, start=timedelta(hours=11), end=timedelta(hours=11 + 8)),
            WorkoutPeriod(day_of_week=calendar.TUESDAY, start=timedelta(hours=11), end=timedelta(hours=11 + 8)),
            WorkoutPeriod(day_of_week=calendar.WEDNESDAY, start=timedelta(hours=11), end=timedelta(hours=11 + 8)),
            WorkoutPeriod(day_of_week=calendar.THURSDAY, start=timedelta(hours=11), end=timedelta(hours=11 + 8)),
            WorkoutPeriod(day_of_week=calendar.FRIDAY, start=timedelta(hours=11), end=timedelta(hours=11 + 8)),
            WorkoutPeriod(day_of_week=calendar.SATURDAY, start=timedelta(hours=13), end=timedelta(hours=13 + 8)),
            WorkoutPeriod(day_of_week=calendar.SUNDAY, start=timedelta(hours=13), end=timedelta(hours=13 + 5)),
        ]
    )
    session.add(wp)
    await session.commit()


async def get_andrew_workout_plan(session):
    stmt = select(WorkoutPlan).where(WorkoutPlan.name.is_("Andrew's Workout Plan"))
    for wp in await session.scalars(stmt):
        return wp


def generate_sample_week_increments():
    current = datetime.now()
    current = current.astimezone()
    final = current + timedelta(days=8)
    increment = timedelta(minutes=30)
    jitter = timedelta(minutes=30)
    while current <= final:
        yield current
        current += increment
        current += timedelta(seconds=random.randint(0, jitter.seconds))


async def generate_sample_week(workout_plan):
    workout = Workout(workout_plan)
    for now in generate_sample_week_increments():
        action = workout.pick_action_for(now)
        if action:
            yield action


def shuffle_but_keep_time(actions):
    originals = [copy(a.time) for a in actions]
    random.shuffle(actions)
    for original, action in zip(originals, actions):
        action.time = original


async def generate_sample_week_with_day_randomization(workout_plan):
    """Generate a sample week in which a whole day is planned and then the workouts for that day are randomized.
    This avoids always front-loading the goal exercises and ending with the non-goal exercises
    """
    workout = Workout(workout_plan)
    for now in generate_sample_week_increments():
        await workout.pick_action_for(now)
    current_day = workout.actions[0].time.weekday()
    day_randomized_actions = []
    this_day_actions = []
    for action in workout.actions:
        if action.time.weekday() != current_day:
            shuffle_but_keep_time(this_day_actions)
            day_randomized_actions.extend(this_day_actions)
            current_day = action.time.weekday()
            this_day_actions = []
        this_day_actions.append(action)
    if 0 != len(this_day_actions):
        shuffle_but_keep_time(this_day_actions)
        day_randomized_actions.extend(this_day_actions)
    for action in day_randomized_actions:
        yield action


async def main():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=True, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine) as session:
        await andrew_workout_plan(session)

    async with AsyncSession(engine) as session:
        wp = await get_andrew_workout_plan(session)
        async for action in generate_sample_week_with_day_randomization(wp):
            print(f"On {action.time} do {action.exercise.name} for {action.reps} reps and {action.sets} sets")


run(main)
