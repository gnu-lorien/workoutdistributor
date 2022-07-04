from anyio import run

from dataclasses import dataclass
from datetime import timedelta, datetime
from typing import List, Dict
from pprint import pprint
from copy import copy
import calendar
import random
import appdirs

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import text, DateTime, Table, select, Text
from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Integer, Unicode, Interval, UnicodeText
from sqlalchemy.orm import declarative_base, Session, selectinload
from sqlalchemy.orm import relationship

Base = declarative_base()


class Zone(Base):
    """Different shared muscle groups or exercise types

    One zone could represent cardio, and another muscles.

    A more fine-grained approach could define individual muscle groups and types of cardio.
    """
    __tablename__ = "zone"
    id = Column(Integer, primary_key=True)

    name = Column(Unicode(30))
    description = Column(UnicodeText())


class Exercise(Base):
    __tablename__ = "exercise"
    id = Column(Integer, primary_key=True)

    name = Column(Unicode(30))  # Short name of the workout
    description = Column(UnicodeText())  # Description of the details of the workout
    rep_description = Column(UnicodeText())  # Description of what counts as 1 rep
    url = Column(Text(2048))

    minimum_reps = Column(Integer())
    maximum_reps = Column(Integer())
    minimum_sets = Column(Integer())
    maximum_sets = Column(Integer())

    minimum_timedelta_between = Column(Interval())  # Minimum amount of time to put between each time of this exercise
    maximum_timedelta_between = Column(Interval())  # Maximum amount of time to put between each time of this exercise

    zone_id = Column(Integer(), ForeignKey("zone.id"))
    zone = relationship("Zone", lazy="selectin")

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
    """A plan of exercises to try to do.

    Exercises can be grouped by their minimums and maximums, which come from the exercise definitions themselves, or by
    zones. This allows a workout to group zones on certain days and to also put time between zones on different days.
    """
    __tablename__ = "workout_plan"
    id = Column(Integer, primary_key=True)

    name = Column(Unicode(30))
    exercises = relationship("Exercise", secondary=workout_plan_to_exercises_association_table, lazy="selectin")
    periods = relationship("WorkoutPeriod", secondary=workout_plan_to_workout_periods_association_table,
                           lazy="selectin")
    minimum_timedelta_between_zones = Column(Interval())


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


def andrew_exercises(session):
    plantar = Zone(name="Plantar Fasciitis")
    sciatica = Zone(name="Sciatica")
    core_one = Zone(name="Core 1 Plan", description="Slipped neck disk original plan")
    core_two = Zone(name="Core 2 Plan", description="Slipped neck disk second plan")
    core_three = Zone(name="Core 3 Plan", description="Slipped neck disk third plan")
    session.add_all([plantar, sciatica, core_one, core_two, core_three])
    return [
        Exercise(
            name="Planks with Protraction",
            description="Perform a plank by keeping your abdominals tight and pushing up through your forearms. You should be able to draw a straight line from your ankles, through your hips to your shoulders. Once in a plank position, attempt to push up higher through your forearms, arching your upper back. Slowly lower back to the plank position. Repeat as directed.",
            rep_description="1 protraction while in plank position",
            minimum_reps=10,
            maximum_reps=10,
            minimum_sets=2,
            maximum_sets=3,
            minimum_timedelta_between=timedelta(hours=16),
            maximum_timedelta_between=timedelta(days=2),
            goals=[GoalPeriod(period=timedelta(days=2), reps_per_period=20, sets_per_period=2)],
            zone=core_one
        ),
        Exercise(
            name="Bilateral Shoulder External Rotation & Retraction With Resistance Band",
            description="Holding a short exercise band in both hands, and standing up straight with your back straight, bend your elbows so that they are at 90 degrees and squeeze your elbows in to your sides. Keeping your elbows at your sides, rotate your arms outwards, bringing your hands apart. Squeeze your shoulder blades together as you do so. Repeat as directed.",
            rep_description="5 second hold",
            minimum_reps=10,
            maximum_reps=15,
            minimum_sets=2,
            maximum_sets=2,
            minimum_timedelta_between=timedelta(hours=1),
            maximum_timedelta_between=timedelta(hours=2),
            goals=[GoalPeriod(period=timedelta(days=2), reps_per_period=20, sets_per_period=4)],
            zone=core_one
        ),
        Exercise(
            name="Dumbell D2 Flexion with a band instead (drawing sword)",
            description="Starting Position: Stand with your arms in an X-position, crossed over each other at your wrists, palms facing inward, holding a dumbbell in each. Movement: Making sure that your arms stay straight, elevate your arms out and overhead to make a and “Y” position. Then slowly lower them down. Tip: Make sure you don't arch your back as you lift your arms overhead.",
            rep_description="5 second hold",
            minimum_reps=10,
            maximum_reps=15,
            minimum_sets=2,
            maximum_sets=3,
            minimum_timedelta_between=timedelta(hours=1),
            maximum_timedelta_between=timedelta(hours=2),
            goals=[GoalPeriod(period=timedelta(days=2), reps_per_period=20, sets_per_period=4)],
            zone=core_one
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
            goals=[GoalPeriod(period=timedelta(weeks=1), reps_per_period=1, sets_per_period=1)],
            zone=core_one
        ),
        Exercise(
            name="Supine Shoulder Horizontal Abduction With Resistance Band",
            description="Starting Position: -Begin by lying on your back in the hooklying position. Grasp a band shoulder width apart with your arms extended straight towards the ceiling. Movement: -Stretch the band by slowly moving your hands away from each other towards the floor while keeping your arms straight. At the end of the motion your trunk and arms will form the shape of a T. Pause, then lift your hips toward the ceiling in a bridge and hold 5 seconds (not shown) Slowly return to the starting position. Repeat as prescribed. Tip: -Keep your shoulder blade squeezed down and back throughout the exercise and avoid shrugging. Hold a slight chin tuck.",
            rep_description="5 second hold",
            minimum_reps=10,
            maximum_reps=10,
            minimum_sets=2,
            maximum_sets=2,
            minimum_timedelta_between=timedelta(hours=1),
            maximum_timedelta_between=timedelta(hours=2),
            goals=[GoalPeriod(period=timedelta(days=2), reps_per_period=20, sets_per_period=4)],
            zone=core_two
        ),
        Exercise(
            name="Supine Shoulder Flexion With Cane Wand",
            description="Lying on your back, hold onto a cane with both hands with your palms facing inwards. Begin with the cane on your stomach and slowly lift over your head while keeping your elbows straight and your back flat on the floor. Pull ribs down toward the surface, then hands toward ceiling. Pause and bring both knees to the bar, while pressing low back into the surface. Lower feet toward the ground without letting your low back come off the surface, and repeat",
            rep_description="1 action",
            minimum_reps=2,
            maximum_reps=10,
            minimum_sets=2,
            maximum_sets=2,
            minimum_timedelta_between=timedelta(days=1),
            maximum_timedelta_between=timedelta(days=3),
            goals=[GoalPeriod(period=timedelta(weeks=1), reps_per_period=10, sets_per_period=2)],
            zone=core_two
        ),
        Exercise(
            name="Serratus Hug With Resistance Band",
            description="Starting Position: Begin standing with a band anchored behind you at chest height. Grasp the ends of the band with both hands. Extend your arms straight out in front of you. Movement: Hold your elbows locked into extension as you reach farther forward with your hands by moving your shoulder blades forward. Then, slowly allow your shoulder blades to squeeze together against the resistance of the band. Repeat as prescribed. Tip: Keep your neck in neutral by holding a slight chin tuck throughout the exercise. unlike the video, take your arms out wide then forward, like you're hugging around a tree, sliding shoulderblades as far away from each other as you can, without lifting shoulders toward your ears.",
            rep_description="5 second hold",
            minimum_reps=10,
            maximum_reps=15,
            minimum_sets=1,
            maximum_sets=2,
            minimum_timedelta_between=timedelta(hours=1),
            maximum_timedelta_between=timedelta(hours=2),
            goals=[GoalPeriod(period=timedelta(days=2), reps_per_period=15, sets_per_period=2)],
            zone=core_two
        ),
        Exercise(
            name="Wall Trapezius Strengthening",
            description="Starting Position: Stand with your back against a wall or doorway. Engage your shoulder blade muscles to bring your scapula down and back, and then place your arms in a 'W' position with your elbows,wrists, and back of hands against the wall. Movement: From this position, move your arms up and down as if making a 'snow angel' while keeping everything in contact with the wall. Be sure to keep head in a chin tuck position. Repeat for as many reps/sets as recommended by your therapist. low back pressed against the wall, feet out from the wall",
            rep_description="5 second hold",
            minimum_reps=10,
            maximum_reps=20,
            minimum_sets=1,
            maximum_sets=2,
            minimum_timedelta_between=timedelta(hours=16),
            maximum_timedelta_between=timedelta(days=3),
            goals=[GoalPeriod(period=timedelta(weeks=1), reps_per_period=20, sets_per_period=2)],
            zone=core_two
        ),
        Exercise(
            name="Shoulder Flexion Serratus Activation With Resistance Band or medball/object",
            description=" Starting Position: Begin in a standing position with your shoulders and elbows flexed to 90 degrees. Place a band loop around your wrists. Movement: Engage your shoulder muscles by stretching the loop until your forearms are vertical at shoulder width apart from each other. Raise your arms up towards the ceiling and return to the starting position without reaching full elbow extension. Repeat as prescribed. Tip: Do not arch your low back during the exercise.",
            rep_description="5 second hold",
            minimum_reps=10,
            maximum_reps=20,
            minimum_sets=1,
            maximum_sets=2,
            minimum_timedelta_between=timedelta(hours=16),
            maximum_timedelta_between=timedelta(days=3),
            goals=[GoalPeriod(period=timedelta(weeks=1), reps_per_period=20, sets_per_period=2)],
            zone=core_two
        ),
        Exercise(
            name="Ulnar Nerve Glide",
            description="Stand up comfortably. Start with your hand down at your side. Lift your hand up sideways to bring it over your ear. Rotate the hand so the fingers point downward when against your ear. To increase the tension, you can push your elbow backward at the end. Do not execute the exercise too fast; the symptoms can arise quickly. Stop the movement at the edge of where your symptoms are reproduced. Remember to only go up to the tingling but not past it. Back off a little bit if the tingling/numbness gets to be too much.",
            rep_description="1 minute",
            minimum_reps=1,
            maximum_reps=1,
            minimum_sets=1,
            maximum_sets=3,
            minimum_timedelta_between=timedelta(hours=16),
            maximum_timedelta_between=timedelta(days=3),
            goals=[GoalPeriod(period=timedelta(weeks=1), reps_per_period=3, sets_per_period=3)],
            zone=core_three
        ),
        Exercise(
            name="Toe Curls With Towel",
            description="Place a small towel on the floor. Using involved foot, curl towel toward you, using only your toes. Relax.",
            rep_description="Place a small towel on the floor. Using involved foot, curl towel toward you, using only your toes. Relax.",
            url="https://www.ortho.wustl.edu/content/Education/3691/Patient-Education/Educational-Materials/Plantar-Fasciitis-Exercises.aspx",
            minimum_reps=10,
            maximum_reps=10,
            minimum_sets=1,
            maximum_sets=1,
            minimum_timedelta_between=timedelta(hours=4),
            maximum_timedelta_between=timedelta(days=2),
            goals=[GoalPeriod(period=timedelta(days=2), reps_per_period=20, sets_per_period=2)],
            zone=plantar
        ),
        Exercise(
            name="Toe Extension",
            description="Sit with involved leg crossed over uninvolved leg. Grasp toes with one hand and bend the toes and ankle upwards as far as possible to stretch the arch and calf muscle. With the other hand, perform deep massage along the arch of your foot.",
            rep_description="Hold 10 seconds.",
            url="https://www.ortho.wustl.edu/content/Education/3691/Patient-Education/Educational-Materials/Plantar-Fasciitis-Exercises.aspx",
            minimum_reps=6,
            maximum_reps=6,
            minimum_sets=2,
            maximum_sets=3,
            minimum_timedelta_between=timedelta(hours=1),
            maximum_timedelta_between=timedelta(days=2),
            goals=[GoalPeriod(period=timedelta(days=2), reps_per_period=6 * 2, sets_per_period=2 * 2)],
            zone=plantar
        ),
        Exercise(
            name="Standing Calf Stretch",
            description="Stand placing hands on wall for support. Place your feet pointing straight ahead, with the involved foot in back of the other. The back leg should have a straight knee and front leg a bent knee. Shift forward, keeping back leg heel on the ground, so that you feel a stretch in the calf muscle of the back leg.",
            rep_description="Hold 45 seconds.",
            url="https://www.ortho.wustl.edu/content/Education/3691/Patient-Education/Educational-Materials/Plantar-Fasciitis-Exercises.aspx",
            minimum_reps=2,
            maximum_reps=3,
            minimum_sets=2,
            maximum_sets=3,
            minimum_timedelta_between=timedelta(hours=1),
            maximum_timedelta_between=timedelta(days=2),
            goals=[GoalPeriod(period=timedelta(days=2), reps_per_period=4 * 2, sets_per_period=4)],
            zone=plantar
        ),
        Exercise(
            name="Towel Stretch",
            description="""The towel stretch is effective at reducing morning pain if done before getting out of bed.
                           1. Sit with involved leg straight out in front of you. Place a towel around your foot and
                           gently pull toward you, feeling a stretch in your calf muscle.""",
            rep_description="Hold 45 seconds.",
            url="https://www.ortho.wustl.edu/content/Education/3691/Patient-Education/Educational-Materials/Plantar-Fasciitis-Exercises.aspx",
            minimum_reps=2,
            maximum_reps=3,
            minimum_sets=2,
            maximum_sets=3,
            minimum_timedelta_between=timedelta(hours=1),
            maximum_timedelta_between=timedelta(days=2),
            goals=[GoalPeriod(period=timedelta(days=2), reps_per_period=4 * 2, sets_per_period=4)],
            zone=plantar
        ),
        Exercise(
            name="Calf Stretch on a Step",
            description="""Stand with uninvolved foot flat on a step. Place involved ball of foot on the edge of the step. Gently let heel lower on involved leg to feel a stretch in your calf.""",
            rep_description="Hold 45 seconds.",
            url="https://www.ortho.wustl.edu/content/Education/3691/Patient-Education/Educational-Materials/Plantar-Fasciitis-Exercises.aspx",
            minimum_reps=2,
            maximum_reps=3,
            minimum_sets=2,
            maximum_sets=3,
            minimum_timedelta_between=timedelta(hours=1),
            maximum_timedelta_between=timedelta(days=2),
            goals=[GoalPeriod(period=timedelta(days=2), reps_per_period=4 * 2, sets_per_period=4)],
            zone=plantar
        ),
        Exercise(
            name="Ice Massage Arch Roll",
            description="With involved foot resting on a frozen can or water bottle, golf ball, or tennis ball, roll your foot back and forth over the object. ",
            rep_description="Roll 1 minute",
            url="https://www.ortho.wustl.edu/content/Education/3691/Patient-Education/Educational-Materials/Plantar-Fasciitis-Exercises.aspx",
            minimum_reps=3,
            maximum_reps=5,
            minimum_sets=1,
            maximum_sets=1,
            minimum_timedelta_between=timedelta(hours=4),
            maximum_timedelta_between=timedelta(days=2),
            goals=[GoalPeriod(period=timedelta(days=2), reps_per_period=5, sets_per_period=2)],
            zone=plantar
        ),
        Exercise(
            name="Core marches",
            description="Starting Position: Begin by lying on your back with your knees bent and feet flat on the floor. Movement: Tighten your abdominals and roll your hips backwards, feeling your low back press downwards towards the floor. Keeping your abdominals tight, alternate lifting your feet off the floor keeping your knees bent as if you are marching in place. Repeat as prescribed. Tip: Do not allow your low back to arch.",
            rep_description="1 march",
            minimum_reps=10,
            maximum_reps=10,
            minimum_sets=1,
            maximum_sets=3,
            minimum_timedelta_between=timedelta(hours=1),
            maximum_timedelta_between=timedelta(hours=2),
            goals=[GoalPeriod(period=timedelta(weeks=1), reps_per_period=30, sets_per_period=3)],
            zone=sciatica
        ),
        Exercise(
            name="Bridges",
            description=" Begin by lying with knees bent and both feet placed on the floor with arms at your sides. Raise your hips off the surface by squeezing your gluteal muscles. Attempt to bring the hips up to where they are in line between the knees and shoulders. Repeat as directed.",
            rep_description="1 bridge",
            minimum_reps=10,
            maximum_reps=10,
            minimum_sets=1,
            maximum_sets=3,
            minimum_timedelta_between=timedelta(hours=16),
            maximum_timedelta_between=timedelta(days=2),
            goals=[GoalPeriod(period=timedelta(days=2), reps_per_period=20, sets_per_period=2)],
            zone=sciatica
        ),
        Exercise(
            name="Clamshells with resistance band",
            description="Begin by lying on your side with the side you intend to exercise upwards with an exercise band tied around your thighs. With your knees bent and feet together, slowly pull your knees apart, keeping your feet together. Hold as directed. Slowly bring your knees back together. Repeat as directed.",
            rep_description="1 clamshell on left and right side",
            minimum_reps=10,
            maximum_reps=10,
            minimum_sets=1,
            maximum_sets=3,
            minimum_timedelta_between=timedelta(hours=2),
            maximum_timedelta_between=timedelta(hours=4),
            goals=[GoalPeriod(period=timedelta(days=2), reps_per_period=30, sets_per_period=3)],
            zone=sciatica
        ),
        Exercise(
            name="Farmer's carry",
            description="Starting Position: Standing, holding desired KB in both arms at side. Movement: Walk desired distance while holding kettlebell's at side. Tip: Maintain height throughout walk, with good posture.",
            rep_description="1 minute of walking with 25lbs resistance",
            minimum_reps=1,
            maximum_reps=1,
            minimum_sets=2,
            maximum_sets=4,
            minimum_timedelta_between=timedelta(hours=16),
            maximum_timedelta_between=timedelta(days=7),
            goals=[GoalPeriod(period=timedelta(weeks=1), reps_per_period=4, sets_per_period=4)],
            zone=sciatica
        ),
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
            goals=[GoalPeriod(period=timedelta(weeks=1), reps_per_period=30, sets_per_period=3)],
            zone=sciatica
        ),
        Exercise(
            name="Kettlebell RDL (Romanian Deadlift)",
            description="Starting Position: Begin by standing tall with feet shoulder width apart and knees unlocked. KB starts between your feet with the handle of kettlebell lining up with your ankles. Movement: Proceed into a hip hinging motion sitting hips back while maintaining natural curve of your back and reach for handle of kettlebell. Once gripped engage your core and lock your shoulder blades down and back. This should cause the kettlebell to hover slightly off the floor even before you start the motion. Extend upwards through your hips, using your hamstrings and glutes, spine in neutral the whole movement. Tip: Try not to bend knees to get depth, Try to keep hips square. Finish tall with glutes, but do not throw hips forward at top.",
            rep_description="1 deadlift",
            minimum_reps=8,
            maximum_reps=10,
            minimum_sets=1,
            maximum_sets=2,
            minimum_timedelta_between=timedelta(hours=16),
            maximum_timedelta_between=timedelta(days=2),
            goals=[GoalPeriod(period=timedelta(weeks=1), reps_per_period=30, sets_per_period=3)],
            zone=sciatica
        ),
    ]


async def andrew_workout_plan(session):
    wp = WorkoutPlan(
        name="Andrew's Workout Plan",
        exercises=andrew_exercises(session),
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
    print(appdirs.user_data_dir(appname="WorkoutDistributor", roaming=True))
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
