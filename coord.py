# import os

filename = '20140512_10092.res'
sat_N = 95232


class coord(object):
    """coord class"""
    def __init__(self, date=0.0, time=0.0, RA=0.0, DEC=0.0, m=0.0):
        self.date = date
        self.time = time
        self.RA = RA
        self.DEC = DEC
        self.m = m


class seriya(object):
    """Seriya class"""
    def __init__(self, st_id='', ser_id=0, coord=[]):
        self.st_id = ''
        self.ser_id = 0
        self.coord = []


class elements(object):
    """seriya check class"""
    def __init__(self, sat_ID='', a=0, e=0, i=0, W=0, w=0, M=0, Lon=0):
        self.sat_ID = ''
        self.a = 0
        self.e = 0
        self.i = 0
        self.W = 0
        self.w = 0
        self.M = 0
        self.Lon = 0


def read_res(filename):
    '''
    :param filename: file name
    :return: a_ser - array of seriya class
    '''
    ser_a = []
    file = open(filename, 'r')
    serN = 0
    # ser = [punkt, id, coord]
    for line in file:
        l = line.split()
        if len(l) == 3:
            ser = seriya()
            ser.st_id = int(l[1])
            ser.ser_id = int(l[2])
        elif len(l) == 5:
            date = int(l[0])
            time = float(l[1][:2])+float(l[1][2:4])/60+(float(l[1][4:8])/100)/3600
            RA = float(l[2][:2])+float(l[2][2:4])/60+(float(l[2][4:8])/100)/3600
            DEC_i = float(l[3][:3])
            DEC_f = float(l[3][3:5])/60+(float(l[3][5:9])/100)/3600
            if DEC_i >= 0:
                DEC = DEC_i + DEC_f
            else:
                DEC = DEC_i - DEC_f
            m = float(l[4])/100
            c = coord(date, time, RA, DEC, m)
            ser.coord.append(c)
        else:
            if line != '' and len(l) == 0:
                ser_a.append(ser)
                serN += 1
    print serN, ' series in file ', filename
    file.close()
    return ser_a


def read_check(fname):
    '''
    :param fname: file name
    :return: check, check_match - array of elements class
    '''
    a_check = []
    a_check_match = []
    elem = elements()
    elem_match = elements()
    file = open(fname, 'r')
    for line in file:
        if line[0] == '-':
            satID = line.split()[3].split(')')[0]
            # print ''
            # print satID
            elem.sat_ID = satID
        elif line[:3] == '  a':
            a = line.split()[1]
            nl = file.next()
            a_match = nl.split()[0]
            # print a, a_match
            elem.a = float(a)
            elem_match.a = float(a_match)
            elem_match.sat_ID = nl.split()[-1][1:-1]
            # print satID, ' match=', elem_match.sat_ID
        elif line[:3] == '  e':
            e = line.split()[1]
            nl = file.next()
            e_match = nl.split()[0]
            # print e, e_match
            elem.e = float(e)
            elem_match.e = float(e_match)
        elif line[:3] == '  i':
            i = line.split()[1]
            nl = file.next()
            i_match = nl.split()[0]
            # print i, i_match
            elem.i = float(i)
            elem_match.i = float(i_match)
        elif line[:3] == '  W':
            W = line.split()[1]
            nl = file.next()
            W_match = nl.split()[0]
            # print W, W_match
            elem.W = float(W)
            elem_match.W = float(W_match)
        elif line[:3] == '  w':
            w = line.split()[1]
            nl = file.next()
            w_match = nl.split()[0]
            # print w, w_match
            elem.w = float(w)
            elem_match.w = float(w_match)
        elif line[:3] == '  M':
            M = line.split()[1]
            nl = file.next()
            M_match = nl.split()[0]
            # print M, M_match
            elem.M = float(M)
            elem_match.M = float(M_match)
        elif line[:3] == 'Lon':
            Lon = line.split()[4]
            # print Lon
            elem.Lon = float(Lon)
            elem_match.Lon = float(Lon)
            a_check.append(elem)
            a_check_match.append(elem_match)
            elem = elements()
            elem_match = elements()
    file.close()
    return a_check, a_check_match


# ser_a = read_res(filename)
