Development Setup
----------
0. Install nginx on the same machine as ejabberd (that has the vine.im URL)
  * `wget http://nginx.org/download/nginx-1.2.0.tar.gz`
  * `gunzip -c nginx-1.2.0.tar.gz | tar xf -`
  * `cd nginx-1.2.0`
  * `sudo /usr/local/nginx/sbin/nginx `  # to start nginx
  * Get the favicon from dropbox and put it in `/usr/local/nginx/html/`
0. Optionally set up the vine.im home page form
  * `sudo vim /usr/local/nginx/html/index.html`
0. Install necessary Perl modules
  * `sudo yum install cpan`
  * `cpan`
  * `o conf urllist`  # Make sure there are valid mirrors, and if not, try adding the following
  * `o conf urllist push http://cpan.strawberryperl.com/`
  * `o conf commit`
  * Control-d to leave the cpan prompt
  * `sudo cpan Locale::Maketext::Fuzzy`  # And repeat for any other necessary modules, noting that error messages like "Can't locate Locale/Maketext/Fuzzy.pm in @INC" mean you should try commands like the one mentioned
0. Fetch, configure, and install JWChat
  * `git clone git@github.com:lehrblogger/vine-jwchat.git jwchat`
  * `sudo sh install.sh [vine.im or dev.vine.im] [username] [password] [random string for URL] [optional debug flag]`

Known Bugs
----------
  * Topics in roster are not removed when cleared.
  * Fix ampersands being displayed as &amp; in chat window title bars.

Google Form HTML (for lack of a better place to put it)
----------
<!DOCTYPE html>
<html lang="en">
	<head>
		<meta charset="utf-8" />
		<title>Vine.IM</title>
	</head>
	<body>
		<iframe src="https://docs.google.com/spreadsheet/embeddedform?formkey=dEduRlNBODVMMjBqZE8xdmZTYWc3aHc6MQ" width="760" height="1541" frameborder="0" marginheight="0" marginwidth="0">Loading...</iframe>
	</body>
</html>
