filename = '20140512_10092.res'
sat_N = 95232

from coord import *

res = read_res(filename)
check, check_match = read_check(filename+'.check')
print res[1].ser_id, check_match[1].sat_ID, check[1].a, check_match[1].a
