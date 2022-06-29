from dataclasses import dataclass
from datetime import timedelta, datetime
from typing import List, Dict
from pprint import pprint
import calendar


@dataclass
class GoalPeriod:
    period: timedelta  # The period of time we hope to achieve these within
    reps_per_period: int  # Number of reps we hope to do within a certain period
    sets_per_period: int  # Number of sets we hope to do within a certain period


@dataclass
class Exercise:
    name: str  # Short name of the workout
    description: str  # Description of the details of the workout
    rep_description: str  # Description of what counts as 1 rep

    minimum_reps: int
    maximum_reps: int
    minimum_sets: int
    maximum_sets: int

    minimum_timedelta_between: timedelta  # Minimum amount of time to put between each time of this exercise
    maximum_timedelta_between: timedelta  # Maximum amount of time to put between each time of this exercise

    goals: List[GoalPeriod]


@dataclass
class WorkoutPeriod:
    start: timedelta
    end: timedelta


@dataclass
class WorkoutPlan:
    name: str
    exercises: List[Exercise]
    periods: Dict[int, WorkoutPeriod]


@dataclass
class Action:
    time: datetime
    reps: int
    sets: int
    exercise: Exercise


class Workout:
    def __init__(self, workout_plan):
        self.workout_plan = workout_plan
        self.actions = []

    def is_exercise_available(self, now, exercise):
        for action in reversed(self.actions):
            if action.exercise == exercise:
                if (now - action.time) < exercise.minimum_timedelta_between:
                    return False
        return True

    def pick_action_for(self, now):
        # Don't do any selecting if outside of the workout hours
        # Gather all available exercises
        available = [e for e in self.workout_plan.exercises if self.is_exercise_available(now, e)]
        if 0 == len(available):
            return None
        a = Action(exercise=available[0], time=now, reps=0, sets=0)
        self.actions.append(a)
        # Find all exercises with an unmet goal
        # Pick an unmet exercise first
        # Find all exercises with no goals or met goals
        # Pick one
        return a


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


def andrew_workout_plan():
    return WorkoutPlan(
        name="Andrew's Workout Plan",
        exercises=andrew_exercises(),
        periods={
            calendar.MONDAY: WorkoutPeriod(timedelta(hours=11), timedelta(hours=11 + 8)),
            calendar.TUESDAY: WorkoutPeriod(timedelta(hours=11), timedelta(hours=11 + 8)),
            calendar.WEDNESDAY: WorkoutPeriod(timedelta(hours=11), timedelta(hours=11 + 8)),
            calendar.THURSDAY: WorkoutPeriod(timedelta(hours=11), timedelta(hours=11 + 8)),
            calendar.FRIDAY: WorkoutPeriod(timedelta(hours=11), timedelta(hours=11 + 8)),
            calendar.SATURDAY: WorkoutPeriod(timedelta(hours=13), timedelta(hours=13 + 8)),
            calendar.SUNDAY: WorkoutPeriod(timedelta(hours=13), timedelta(hours=13 + 5)),
        }
    )


def generate_sample_week_increments():
    current = datetime.now()
    final = current + timedelta(days=8)
    increment = timedelta(minutes=30)
    while current <= final:
        yield current
        current += increment


def generate_sample_week(workout_plan):
    workout = Workout(workout_plan)
    for now in generate_sample_week_increments():
        action = workout.pick_action_for(now)
        if action:
            yield action


def main():
    pprint(list(generate_sample_week(andrew_workout_plan())))


main()
