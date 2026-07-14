/* Vendored from tw-kang/skills@develop (0cb5ba2), cubrid-shell-tc-create/examples/cci_crash_repro.c */
/*
 * Minimal CCI client for a CAS crash / session-reuse repro.
 *
 * Demonstrates the pattern, not a specific bug: connect -> prepare -> execute
 * -> disconnect, repeated, so one reused CAS process handles many cycles.
 * Real repros vary the statement (e.g. CALL a stored procedure that opens a
 * cursor) and may alternate between two databases on the same broker.
 *
 * Built at test time by the entry script with the CTP xgcc helper:
 *   xgcc -o cci_crash_repro cci_crash_repro.c
 * which supplies -I$CUBRID/include -L$CUBRID/lib -lcascci -lpthread and the
 * 32/64-bit + OS flags. Include the installed header, not a source-tree path.
 *
 * Usage: cci_crash_repro <host> <port> <dbname> <iterations>
 * Exit:  0 = every cycle succeeded, non-zero = a call failed (a crash symptom).
 */

#include <stdio.h>
#include <stdlib.h>

#include "cas_cci.h"

static void
print_error (T_CCI_ERROR *err)
{
  if (err->err_code != 0)
    fprintf (stderr, "CCI error %d: %s\n", err->err_code, err->err_msg);
}

static int
one_cycle (const char *host, int port, const char *db)
{
  T_CCI_ERROR err;
  int conn, req, rc;
  char user[] = "dba";
  char pass[] = "";

  conn = cci_connect_ex ((char *) host, port, (char *) db, user, pass, &err);
  if (conn < 0)
    {
      fprintf (stderr, "connect failed to %s:%d/%s\n", host, port, db);
      print_error (&err);
      return -1;
    }

  req = cci_prepare (conn, "SELECT 1", 0, &err);
  if (req < 0)
    {
      print_error (&err);
      cci_disconnect (conn, &err);
      return -1;
    }

  rc = cci_execute (req, 0, 0, &err);
  if (rc < 0)
    print_error (&err);

  cci_close_req_handle (req);
  rc = cci_disconnect (conn, &err);
  return (rc < 0) ? -1 : 0;
}

int
main (int argc, char *argv[])
{
  const char *host, *db;
  int port, iterations, i;

  if (argc < 5)
    {
      fprintf (stderr, "Usage: %s <host> <port> <dbname> <iterations>\n", argv[0]);
      return 1;
    }
  host = argv[1];
  port = atoi (argv[2]);
  db = argv[3];
  iterations = atoi (argv[4]);

  for (i = 1; i <= iterations; i++)
    {
      if (one_cycle (host, port, db) != 0)
        {
          fprintf (stderr, "failed on iteration %d\n", i);
          return 1;
        }
    }

  printf ("completed %d iterations\n", iterations);
  return 0;
}
