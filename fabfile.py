from os.path import join
from fabric.api import run, env, local, sudo, put, require, cd
from fabric.contrib.project import rsync_project
from fabric import utils
from fabric.contrib import console
from fabric.context_managers import prefix


RSYNC_EXCLUDE = (
    '.bzr',
    '.bzrignore',
    '.git',
    '.gitignore',
    '*.pyc',
    '*.example',
    '*.db',
    'media',
    'static',
    'local_settings.py',
    'fabfile.py',
    'bootstrap.py',
    'tags',
    'lutris_client',
    'PYSMELL*'
)

env.project = 'lutrisweb'
env.home = '/srv/django'


def _setup_path():
    env.root = join(env.home, env.domain)
    env.code_root = join(env.root, env.project)


def staging():
    """ use staging environment on remote host"""
    env.user = 'django'
    env.environment = 'staging'
    env.domain = 'dev.lutris.net'
    env.hosts = [env.domain]
    _setup_path()


def production():
    """ use production environment on remote host"""
    env.user = 'django'
    env.environment = 'production'
    env.domain = 'lutris.net'
    env.hosts = [env.domain]
    _setup_path()


def activate():
    return prefix('. %s/bin/activate' % env.root)


def touch_wsgi():
    """Touch wsgi file to trigger reload."""
    conf_dir = join(env.code_root, 'config')
    with cd(conf_dir):
        run('touch lutrisweb.wsgi')


def apache_reload():
    """ reload Apache on remote host """
    sudo('service apache2 reload', shell=False)


def supervisor_restart():
    """ Reload Supervisor service """
    sudo('service supervisor restart', shell=False)


def test():
    local("python manage.py test games")
    local("python manage.py test accounts")


def initial_setup():
    """Setup virtualenv"""
    run("mkdir -p %s" % env.root)
    with cd(env.root):
        run('virtualenv --no-site-packages .')


def requirements():
    require('environment', provided_by=('staging', 'production'))
    with cd(env.code_root):
        with activate():
            run('pip install -r config/%s.pip --exists-action=s'
                % env.environment)


def update_vhost():
    tempfile = "/tmp/%(project)s.conf" % env
    local('cp config/lutrisweb.conf ' + tempfile)
    local('sed -i s#%%ROOT%%#%(root)s#g ' % env + tempfile)
    local('sed -i s/%%PROJECT%%/%(project)s/g ' % env + tempfile)
    local('sed -i s/%%ENV%%/%(environment)s/g ' % env + tempfile)
    local('sed -i s/%%DOMAIN%%/%(domain)s/g ' % env + tempfile)
    put('/tmp/%(project)s.conf' % env, '%(root)s' % env)
    sudo('cp %(root)s/%(project)s.conf ' % env +
         '/etc/apache2/sites-available/%(domain)s.conf' % env, shell=False)
    sudo('a2ensite %(domain)s.conf' % env, shell=False)


def update_celery():
    tempfile = "/tmp/%(project)s-celery.conf" % env
    local('cp config/lutrisweb-celery.conf ' + tempfile)
    local('sed -i s#%%ROOT%%#%(root)s#g ' % env + tempfile)
    local('sed -i s/%%PROJECT%%/%(project)s/g ' % env + tempfile)
    put(tempfile, '%(root)s' % env)
    sudo('cp %(root)s/lutrisweb-celery.conf ' % env
         + '/etc/supervisor/conf.d/', shell=False)


def rsync():
    """ rsync code to remote host """
    require('root', provided_by=('staging', 'production'))
    if env.environment == 'production':
        if not console.confirm('Are you sure you want to deploy production?',
                               default=False):
            utils.abort('Production deployment aborted.')
    extra_opts = '--omit-dir-times'
    rsync_project(
        env.root,
        exclude=RSYNC_EXCLUDE,
        delete=True,
        extra_opts=extra_opts,
    )


def copy_local_settings():
    require('code_root', provided_by=('staging', 'production'))
    put('config/local_settings_%(environment)s.py' % env, env.code_root)
    with cd(env.code_root):
        run('mv local_settings_%(environment)s.py local_settings_template.py'
            % env)


def migrate():
    require('code_root', provided_by=('staging', 'production'))
    with cd(env.code_root):
        run("source ../bin/activate; "
            "python manage.py migrate --no-initial-data")


def syncdb():
    require('code_root', provided_by=('staging', 'production'))
    with cd(env.code_root):
        run("source ../bin/activate; "
            "python manage.py syncdb --noinput")


def clone():
    with cd(env.root):
        run("git clone /srv/git/lutrisweb")


def pull():
    with cd(env.code_root):
        run("git pull")


def npm():
    with cd(env.code_root):
        run("npm install")


def bower():
    with cd(env.code_root):
        run("bower install")


def grunt():
    with cd(env.code_root):
        run("grunt")


def collect_static():
    require('code_root', provided_by=('stating', 'production'))
    with cd(env.code_root):
        run('source ../bin/activate; python manage.py collectstatic --noinput')


def fix_perms(user='www-data', group=None):
    if not group:
        group = env.user
    with cd(env.code_root):
        sudo('chown -R %s:%s static' % (user, group))
        sudo('chmod -R ug+w static')
        sudo('chown -R %s:%s media' % (user, group))
        sudo('chmod -R ug+w media')


def configtest():
    sudo("apache2ctl configtest")


def authorize(ip):
    with cd(env.code_root):
        with activate():
            run('./manage.py authorize %s' % ip)


def docs():
    with cd(env.code_root):
        run("make client")
        with activate():
            run("make docs")


def deploy():
    fix_perms(user='django')
    pull()
    bower()
    grunt()
    requirements()
    collect_static()
    syncdb()
    migrate()
    docs()
    fix_perms()
    update_vhost()
    configtest()
    apache_reload()
    update_celery()
    supervisor_restart()


def fastdeploy():
    pull()
    bower()
    grunt()
    collect_static()
    touch_wsgi()
