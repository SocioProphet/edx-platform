import datetime
import json
import pytz

from courseware.views import *
from instructor.offline_gradecalc import student_grades
from collections import OrderedDict

log = logging.getLogger("mitx.module_tree_reset")

#-----------------------------------------------------------------------------

class TreeNode(object):
    def __init__(self, module, level, student):
        self.module = module
        self.level = level
        self.student = student
        self.smstate = None
        if self.module.category in ['randomize', 'problem', 'problemset']:
            try:
                self.smstate = StudentModule.objects.get(module_state_key=str(self.module.location), student=student)
            except StudentModule.DoesNotExist:
                pass

    def __str__(self):
        s = "-"*self.level + ("> %s" % str(self.module.location))
        s += '  (%s)' % self.module.display_name

        if self.smstate is not None:
            s += ' [%s]' % self.smstate.state
        return s

    __repr__ = __str__


class TreeNodeSet(list):

    def __init__(self, module, ms, student):
        list.__init__(self)
        self.parent_module = module
        self.student = student
        self.get_tree(module, ms)
        self.get_modules_to_reset()

    def get_tree(self, module, ms, level=1):
        self.append(TreeNode(module, level, self.student))
        for child in getattr(module, 'children', []):
            m = ms.get_item(child)
            if m is not None:
                self.get_tree(m, ms, level+1)

    def get_modules_to_reset(self):
        self.rset = []
        self.pset = []
        for tn in self:
            if tn.module.category=='randomize':
                self.rset.append(tn)
            elif tn.module.category in ['problem', 'problemset']:
                self.pset.append(tn)

    def reset_randomization(self):
        '''
        Go through all <problem> and <randomize> modules in tree and reset their StudentModule state to empty.
        '''
        msg = "Resetting all <problem> and <randomize> in tree of parent module %s\n" % self.parent_module
        for module in self.rset + self.pset:
            msg += "    Resetting %s, old state=%s\n" % (module, (module.smstate.state if module.smstate is not None else {}))
            if module.smstate is not None:
                module.smstate.state = '{}'
                module.smstate.grade = None
                module.smstate.save()
        return msg

#-----------------------------------------------------------------------------

class DummyRequest(object):
    META = {}
    def __init__(self):
        return
    def get_host(self):
        return 'edx.mit.edu'
    def is_secure(self):
        return False

#-----------------------------------------------------------------------------

class ProctorModuleInfo(object):

    def __init__(self, course_loc=''):
        if not course_loc:
            course_loc = 'i4x://MITx/3.091r-exam/course/2013_Fall_residential_exam'
        self.ms = modulestore()
        self.course = self.ms.get_item(course_loc)
        self.get_released_proctor_modules()

    def get_released_proctor_modules(self):
        chapters = []

        for loc in self.course.children:
            chapters.append(self.ms.get_item(loc))

        #print "chapters:"
        #print [c.id for c in chapters]

        pmods = []
        for c in chapters:
            seq = self.ms.get_item(c.children[0])
            if seq.category=='proctor':
                pmods.append(seq)

        #print "proctor modules:"
        #print [x.id for x in pmods]

        now = datetime.datetime.now(pytz.utc)
        rpmods = [p for p in pmods if p.lms.start < now]

        for rpmod in rpmods:
            rpmod.ra_ps = self.ms.get_item(rpmod.children[0])	# the problemset
            rpmod.ra_rand = self.ms.get_item(rpmod.ra_ps.children[0])	# the randomize
            # rpmod.ra_prob = self.ms.get_item(rpmod.ra_rand.children[0])	# the problem

        #print "released pmods"
        #print [x.id for x in rpmods]

        self.chapters = chapters
        self.pmods = pmods
        self.rpmods = rpmods
        return rpmods

    def get_grades(self, student=None, request=None):
        if student is None:
            student = self.student

        if request is None:
            request = DummyRequest()
            request.user = student
            request.session = {}

        try:
            gradeset = student_grades(student, request, self.course, keep_raw_scores=False, use_offline=False)
        except Exception as err:
            #log.exception("Failed to get grades for %s" % student)
            print("Failed to get grades for %s" % student)
            gradeset = []

        self.gradeset = gradeset
        return gradeset

    def get_student_status(self, student):
        '''
        For a given student, and for all released proctored modules, get StudentModule state for each, and
        see which randomized problem was selected for a student (if any).
        '''
        if isinstance(student, str):
            student = User.objects.get(username=student)
        self.student = student

        smstates = OrderedDict()

        # temporary - for debugging; flushes db cache
        if False:
            from django.db import transaction
            try:
                transaction.commit()
            except Exception as err:
                print "db cache flushed"

        class StateInfo(object):
            def __init__(self):
                self.state = '{}'
                return

        for rpmod in self.rpmods:	# assume <proctor><problemset><randomized/></problemset></prcotor> structure
            try:
                sm = StudentModule.objects.get(module_state_key=str(rpmod.ra_rand.location), student=student)	# randomize state
            except StudentModule.DoesNotExist:
                sm = StateInfo()
            sm.rpmod = rpmod
            try:
                ps_sm = StudentModule.objects.get(module_state_key=str(rpmod.ra_ps.location), student=student)	# problemset state
            except StudentModule.DoesNotExist:
                ps_sm = StateInfo()
            sm.ps_sm = ps_sm
            sm.score = None

            # get title (display_name) of problem assigned, if student had started a problem
            # base this on the "choice" from the randmize module state
            try:
                sm.choice = int(json.loads(sm.state)['choice'])
            except Exception as err:
                sm.choice = None
            if sm.choice is not None:
                try:
                    sm.problem = self.ms.get_item(rpmod.ra_rand.children[sm.choice])
                    sm.problem_name = sm.problem.display_name
                except Exception as err:
                    log.exception("Failed to get rand child choice=%s for %s student=%s" % (sm.choice, rpmod.ra_rand, student))
                    sm.problem = None
                    sm.problem_name = None
            else:
                sm.problem = None
                sm.problem_name = None

            smstates[rpmod.url_name] = sm	# the url_name should be like 'LS1' and be the same key used in the grade scores

        self.smstates = smstates

        # get grades, match gradeset assignments with StudentModule states, and put grades there
        self.get_grades()
        for score in self.gradeset['totaled_scores']['Assessment']:
            if score.section in smstates:
                smstates[score.section].score = score

        s = 'State for student %s:\n' % student
        status = {}	# this can be turned into a JSON string for the proctor panel
        status['student'] = dict(username=str(student), name=student.profile.name, id=student.id)
        status['assignments'] = []


        for (name, sm) in smstates.iteritems():

            # attempted = (sm.score is not None)	# this doesn't work, since score will always appear?
            attempted = 'position' in sm.ps_sm.state	# if student has visited the problemset then position will have been set
            if not attempted and sm.score is not None and sm.score.earned:
                attempted = True

            stat = dict(name=name, assignment=sm.rpmod.ra_ps.display_name, pm_sm=sm.ps_sm.state, choice=sm.choice,
                        problem=sm.problem_name,
                        attempted=attempted,
                        earned=(sm.score.earned if sm.score is not None else None),
                        possible=(sm.score.possible if sm.score is not None else None),
                        )
            status['assignments'].append(stat)
            s += "[%s] %s -> %s (%s) %s [%s]\n" % (name, stat['assignment'], stat['pm_sm'], sm.choice, sm.problem_name, sm.score)

        self.status = status
        self.status_str = s

        return status

    def get_student_grades(self, student):
        '''
        Return student grades for assessments as a dict suitable for CSV file output,
        with id, name, username, prob1, grade1, prob2, grade2, ...
        where grade1 = points earned on assignment LS1, or '' if not attempted
        and prob1 = problem which was assigned or '' if not attempted
        '''
        status = self.get_student_status(student)
        ret = OrderedDict()
        ret['id'] = student.id
        ret['name'] = student.profile.name
        # ret['username'] = student.username
        ret['email'] = '%s@mit.edu' % student.username

        for stat in status['assignments']:
            if stat['attempted']:
                ret["problem_%s" % stat['name']] = stat['problem']
                ret["grade_%s" % stat['name']] = stat['earned']
            else:
                ret["problem_%s" % stat['name']] = ''
                ret["grade_%s" % stat['name']] = ''
        return ret

    def get_assignments_attempted_and_failed(self, student, do_reset=False):
        status = self.get_student_status(student)

        assignments = []
        for stat in status['assignments']:
            if stat['attempted']:
                if not stat['earned'] == stat['possible']:
                    s = "Student %s Assignment %s attempted '%s' but failed (%s/%s)" % (student, stat['name'], stat['problem'], stat['earned'], stat['possible'])
                    assignments.append(OrderedDict(id=student.id,
                                                  name=student.profile.name,
                                                  username=student.username,
                                                  assignment=stat['name'],
                                                  problem=stat['problem'],
                                                  date=str(datetime.datetime.now()),
                                                  earned=stat['earned'],
                                                  possible=stat['possible'],
                                                  )
                                       )
                    if do_reset:
                        aaf = assignments[-1]
                        try:
                            log.debug('resetting %s for student %s' % (aaf['assignment'], aaf['username']))
                            pmod = self.ms.get_item('i4x://MITx/3.091r-exam/proctor/%s' % aaf['assignment'])
                            tnset = TreeNodeSet(pmod, self.ms, student)
                            msg = tnset.reset_randomization()
                            log.debug(str(msg))
                        except Exception as err:
                            log.exception("Failed to do reset of %s for %s" % (aaf['assignment'], student))

        return assignments

#-----------------------------------------------------------------------------

def getip(request):
    '''
    Extract IP address of requester from header, even if behind proxy
    '''
    ip = request.META.get('HTTP_X_REAL_IP', '')  	# nginx reverse proxy
    if not ip:
        ip = request.META.get('REMOTE_ADDR', 'None')
    return ip

#-----------------------------------------------------------------------------

ALLOWED_IPS = [ '173.48.139.155', '10.152.159.162', '54.235.195.90' ]
#ALLOWED_IPS = [  ]
ALLOWED_STAFF = 'staff_MITx/3.091r-exam/2013_Fall_residential_exam'

def index(request):

    ip = getip(request)

    if not ip in ALLOWED_IPS:
        if request.user and request.user.is_staff and False:
            log.debug('request allowed because user=%s is staff' % request.user)
        elif request.user is not None and request.user:
            groups = [g.name for g in request.user.groups.all()]

            if ALLOWED_STAFF in groups:
                log.debug('request allowed because user=%s is in group %s' % (request.user, ALLOWED_STAFF))
            else:
                log.debug('request denied, user=%s, groups %s' % (request.user, groups))
                # return HttpResponse('permission denied', status=403)
        else:
            log.debug('request denied, user=%s, groups %s' % (request.user, groups))
            # return HttpResponse('permission denied', status=403)
    else:
        log.debug('request allowed, in ALLOWED_IPS')

    username = request.GET.get('username')

    try:
        student = User.objects.get(username=username)
    except User.DoesNotExist:
        return HttpResponse(json.dumps({'msg':'User does not exist', 'error': True}))

    cmd = request.GET.get('cmd')

    if cmd=='reset':
        location = request.GET.get('location')	# eg     proctor/Assessment_2
        location = location.replace(' ','_')

        ms = modulestore()
        pmod = ms.get_item('i4x://MITx/3.091r-exam/proctor/%s' % location)
        tnset = TreeNodeSet(pmod, ms, student)

        s = ''
        for r in tnset.rset + tnset.pset:
            s += str(r) + '\n'

        msg = tnset.reset_randomization()

        # return render_to_response("module_tree_reset.html", {'status': s, 'msg': msg})
        #cmd = 'grades'
        cmd = 'status'

    if cmd=='status':
        try:
            pminfo = ProctorModuleInfo()
            status = pminfo.get_student_status(student)
        except Exception as err:
            log.exception("Failed to get status for %s" % student)
            return HttpResponse(json.dumps({'msg':'Error getting grades for %s' % student, 'error': True, 'errstr': str(err)}))
        return HttpResponse(json.dumps(status))

    if cmd=='grades':
        # from instructor.offline_gradecalc import student_grades
        ms = modulestore()
        course = ms.get_item('i4x://MITx/3.091r-exam/course/2013_Fall_residential_exam')
        try:
            gradeset = student_grades(student, request, course, keep_raw_scores=False, use_offline=False)
        except Exception as err:
            log.exception("Failed to get grades for %s" % student)
            return HttpResponse(json.dumps({'msg':'Error getting grades for %s' % student, 'error': True}))

        grades = gradeset['totaled_scores']
        grades['student_id'] = student.id
        return HttpResponse(json.dumps(grades))

    return render_to_response("module_tree_reset.html", {'status': 'unknown command', 'msg': ''})
