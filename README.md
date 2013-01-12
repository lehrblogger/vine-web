Like the [vine-web repo](https://github.com/lehrblogger/vine-web), basic configurations of nginx and supervisor are set up by the vine_shared Chef cookbook in the [vine-chef repo](https://github.com/lehrblogger/vine-chef), and this piece of the application expects that cookbook to have run, in addition to the vine-xmpp repo's cookbook. This repo's cookbook adds three supevisor programs, for gunicorn, celeryd, and celerybeat. Gunicorn is the webserver, Celery handles asynchronous tasks for the social graph, and Celerybeat schedules those tasks to run once a day.

Hopefully the code is sufficient to explain how everything is supposed to work, but see the vine-chef repo for more information.
