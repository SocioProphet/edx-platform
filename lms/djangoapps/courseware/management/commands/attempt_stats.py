#!/usr/bin/python
#
# Compute number of times a given problem has been attempted by a student,
# including StudentModuleHistory.  Do this by walking through the course tree.
# For every assessment problem, look up all matching StudehtModuleHistory
# items.  Count number of attempts passed, and number failed.  Remove staff
# data.
#
# Output table with: problem url_id, problem name, number students assigned,
# number attempts failed, number attempts succeeded
#
import csv
import json

from django.core.management.base import BaseCommand, CommandError, make_option

from student import roles
from courseware.module_tree_reset import ProctorModuleInfo
from courseware.models import StudentModule, StudentModuleHistory


class Stats(object):
    def __init__(self):
        self.nassigned = 0
	self.assigned_students = []
        self.nattempts = 0
        self.no_attempt_students = set()
        self.incorrect_students = set()
	self.passed_students = set()
        self.npassed = 0

class AssessmentStats(object):
    def __init__(self, name=None):
        self.assessments = {}
	self.students = set()
        self.name = name

    def set_name(self,name):
        self.name = name

    def add_student(self,name):
        self.assessments[name] = dict()
	self.assessments[name]['assigned_problems'] = set()
	self.assessments[name]['incorrect_problems'] = set()
        self.assessments[name]['passed_problems'] = set()
        self.assessments[name]['no_attempt_problems'] = set()
        self.students.add(name)

    def increment_assigned(self,student,problem):
        if student not in self.students:
            self.add_student(student)
        self.assessments[student]['assigned_problems'].add(problem)
        # print 'incrementing', self.name, 'for', student
        # print 'assigned problems is now', self.assessments[student]['assigned_problems']

    def increment_incorrect(self,student,problem):
        if student not in self.students:
            self.add_student(student)
        self.assessments[student]['incorrect_problems'].add(problem)
        # if student == 'azionts':
        # print 'incrementing incorrects for', self.name, 'for', student
        # print 'incorrect problems is now', self.assessments[student]['incorrect_problems']
        
    def increment_passed(self,student,problem):
        if student not in self.students:
            self.add_student(student)
        self.assessments[student]['passed_problems'].add(problem)
   
    def increment_no_attempt(self,student,problem):
        if student not in self.students:
            self.add_student(student)
        self.assessments[student]['no_attempt_problems'].add(problem)

    def get_rows(self):
        """
        serializes the assessment stats into a list of dicts suitable for csv output
        """
        rows = []
        for student in self.students:
            rows.append(dict(
                pset = self.name,
                student = student,
                assigned = len(self.assessments[student]['assigned_problems']),
                incorrect = len(self.assessments[student]['incorrect_problems']),
                no_attempt = len(self.assessments[student]['no_attempt_problems']),
                passed = len(self.assessments[student]['passed_problems']),
                incorrect_list = list(self.assessments[student]['incorrect_problems']),
                passed_list = list(self.assessments[student]['passed_problems']),    
                no_attempt_list = list(self.assessments[student]['no_attempt_problems']),
            ))

        return rows

def passed(state):
    if 'correct_map' not in state:
        return False
    if not state['correct_map']:
        return False
    # must all be correct to pass
    return all([x['correctness'] == 'correct' for x in
                state.get('correct_map').values()])


def update_stats(sm, stat, assessment_stat, problem, history=False):
    if sm.grade is None:
        # assigned but no grade
        # print 'grade is none for',sm.student
        # print sm
        # stat.no_attempt_students.add(sm.student)
        return
    state = json.loads(sm.state or '{}')
    print state
    if 'input_state' not in state:
        # assigned, but student never saw it
        print 'no input_state in state for', sm.student
        return
    if 'attempts' not in state:
        # assigned but no attempts?
        print 'no attempts in state for',sm.student
        stat.no_attempt_students.add(sm.student)
        return
    if not state.get('done', False):
        print sm.student,'not done'
        print state
        stat.incorrect_students.add(sm.student)
        assessment_stat.increment_incorrect(sm.student,problem.id)
        return "notdone"
    if not history:
        # print "history=",history," state['attempts']=",state['attempts']
        # print state
        stat.nattempts += state['attempts']
    if passed(state):
        stat.passed_students.add(sm.student)
        stat.npassed += 1
        assessment_stat.increment_passed(sm.student,problem.id)
        return "passed"
    else:
        # student must have gotten it wrong
        stat.incorrect_students.add(sm.student)
        assessment_stat.increment_incorrect(sm.student,problem.id)
    return "attempted"


def compute_stats(course_id):
    pminfo = ProctorModuleInfo(course_id)
    all_problems = []
    stats = []
    pset_stats = {}
    course_url = pminfo.course.location.url()
    staff_role = roles.CourseStaffRole(course_url)
    inst_role = roles.CourseInstructorRole(course_url)
    beta_role = roles.CourseBetaTesterRole(course_url)
    exclude_groups = staff_role._group_names + inst_role._group_names + beta_role._group_names

    for rpmod in pminfo.rpmods:
        assignment_set_name = rpmod.ra_ps.display_name
        for ploc in rpmod.ra_rand.children:
            problem = pminfo.ms.get_instance(pminfo.course.id, ploc)
            problem.assignment_set_name = assignment_set_name
            all_problems.append(problem)

    for problem in all_problems[665:685]:
        stat = Stats()
        # create a pset_stats object if one doesn't already exist
        if not pset_stats.get(problem.assignment_set_name,False):
            pset_stats[problem.assignment_set_name] = AssessmentStats(problem.assignment_set_name)
        smset = StudentModule.objects.filter(
            module_state_key=problem.id, student__is_staff=False
        ).exclude(student__groups__name__in=exclude_groups)
        for sm in smset:
            # if sm.student.username == 'tyyan':
            #    print "student:",sm.student
            #    print sm
            smhset = StudentModuleHistory.objects.filter(student_module=sm)
            states = [json.loads(smh.state or '{}') for smh in smhset]
            okset = [passed(x) for x in states]
            attempts = [x.get('attempts', 0) for x in states]
            seen = [x.get('input_state', 0) for x in states]
            # print 'seen', seen
            if sm.student.username == 'mariedea' and problem.assignment_set_name == 'Assessment 29':
                print "29: student:",sm.student
                print sm, states
            if max(seen) > 0:
                stat.nassigned += 1
                pset_stats[problem.assignment_set_name].increment_assigned(sm.student,problem.id)
            else:
                # student never saw the problem
                continue
            if any(okset):
                # student passed
                stat.npassed += 1
                stat.passed_students.add(sm.student)
                pset_stats[problem.assignment_set_name].increment_passed(sm.student,problem.id)
            elif max(attempts) > 0:
                # at least one attempt
                stat.incorrect_students.add(sm.student)
                pset_stats[problem.assignment_set_name].increment_incorrect(sm.student,problem.id)
            elif max(seen) > 0:
                # apparently no attempts
                stat.no_attempt_students.add(sm.student)
                pset_stats[problem.assignment_set_name].increment_no_attempt(sm.student,problem.id)

        print problem.id
        print "    assigned=%d, not attempted=%d, incorrect= %d, passed=%d" % (
            stat.nassigned, len(stat.no_attempt_students), len(stat.incorrect_students), stat.npassed)
        stats.append(dict(
            problem_id=problem.id,
            pset=problem.assignment_set_name,
            problem_name=problem.display_name,
            due=str(problem.due),
            # max_attempts=problem.max_attempts,
            assigned=stat.nassigned,
            # attempts=stat.nattempts,
            no_attempt=len(stat.no_attempt_students),
            incorrect=len(stat.incorrect_students),
            passed=stat.npassed,
        ))
        # assessment_stats.append()
    
    # serialize the assessment stats for making a csv
    pset_stats_output = []
    for pset_name in pset_stats:
        # print 'outputting pset stats for',pset_name
        pset_stats_output.extend(pset_stats[pset_name].get_rows())
 
    return stats, pset_stats_output


def write_stats(stats, csv_filename):
    print "Saving data to %s" % csv_filename
    fieldnames = ['problem_id', 'pset', 'problem_name', 'due',
                  'assigned', 'no_attempt','incorrect', 'passed']
    fp = open(csv_filename, 'w')
    writer = csv.DictWriter(fp, fieldnames, dialect='excel', quotechar='"',
                            quoting=csv.QUOTE_ALL)
    writer.writeheader()
    for row in stats:
        try:
            writer.writerow(row)
        except Exception as err:
            print "Oops, failed to write %s, error=%s" % (row, err)
    fp.close()
    return


def write_assessment_stats(assessment_stats,csv_filename):
    print "Saving data to %s" % csv_filename
    fieldnames = ['pset', 'student', 'assigned', 'incorrect', 'no_attempt',
                  'passed', 'incorrect_list', 
                  'no_attempt_list', 'passed_list']
    fp = open(csv_filename, 'w')
    writer = csv.DictWriter(fp, fieldnames, dialect='excel', quotechar='"',
                            quoting=csv.QUOTE_ALL)
    writer.writeheader()
    for row in assessment_stats:
        try:
            writer.writerow(row)
        except Exception as err:
            print "Oops, failed to write %s, error=%s" % (row, err)
    fp.close()
    return


class Command(BaseCommand):
    args = "<course_id>"
    help = """Generate CSV file with problem attempts statistics; CSV file \
columns include problem id, assigned, max_attempts, attempts, passed for \
every problem in the course.  Arguments: None.  Works only on 3.091-exam"""
    option_list = BaseCommand.option_list + (
        make_option('--csv-output-filename',
                    dest='csv_output_filename',
                    action='store',
                    default=None,
                    help='Save stats to csv file'),
        make_option('--problem-output-filename',
                    dest='problem_output_filename',
                    action='store',
                    default=None,
                    help='Save problem stats to csv file'),
       make_option('--assessment-output-filename',
                    dest='assessment_output_filename',
                    action='store',
                    default=None,
                    help='Save assessment stats to csv file'),
    )

    def handle(self, *args, **options):
        if len(args) != 1:
            raise CommandError("missing argument: <course_id>")
        stats, assessment_stats = compute_stats(args[0])
        csv_output_filename = options['csv_output_filename']
        if csv_output_filename:
            write_stats(stats, csv_output_filename)
        problem_output_filename = options['problem_output_filename']
        if problem_output_filename:
            write_stats(stats, problem_output_filename)
        assessment_output_filename = options['assessment_output_filename']
        if assessment_output_filename:
            write_assessment_stats(assessment_stats, assessment_output_filename)
