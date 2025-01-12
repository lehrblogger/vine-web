maintainer       "Dashdash, Inc."
maintainer_email "lehrburger@gmail.com"
license          "All rights reserved"
description      "Installs/Configures vine_web"
long_description IO.read(File.join(File.dirname(__FILE__), 'README.md'))
version          "1.0.3"

depends "cpan", "= 0.0.29"
depends "deploy_wrapper", "= 0.0.4"
depends "vine_shared", ">= 1.0.0"
depends "vine_ejabberd", ">= 1.0.0"
recommends "vine_xmpp", ">= 1.0.0"
