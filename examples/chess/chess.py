import time
from abc import abstractmethod


from chess_base import board_letters, to_str_pos, to_tuple_pos, get_all_iscales
from chess_base import is_valid_icell, rev_color, color_index, color_sig, to_int_pos


try:
    profile # if run under kernel_prof.py
except NameError:
    def profile(f):
        return f


class ChessPiece(object):
    name = None
    def_cost = None

    precached_moves = {}
    precached_hits = {}

    def __init__(self, pos, color):
        self.ipos = to_int_pos(pos)
        self.color = color
        self.cost = color_sig[self.color] * self.def_cost
        self.eq_id = self.get_eq_id()

    @property
    def pos(self):
        return to_tuple_pos(self.ipos)

    @pos.setter
    def pos(self, value):
        self.ipos = to_int_pos(value)
    
    def move(self, pos):
        assert isinstance(pos, int)
        self.ipos = pos
        self.eq_id = self.get_eq_id()

    @abstractmethod
    def get_move_cells(self):
        pass

    def get_hit_cells(self):
        return self.get_move_cells()

    def hit_cells(self):
        return self.move_cells()

    def move_cells(self):
        eid = self.eq_id
        res = self.precached_moves.get(eid)
        if res is None:
            res = self.get_move_cells()
            self.precached_moves[eid] = res
        return res

    def get_eq_id(self):
        return (self.name, self.ipos)

    def full_name(self):
        return self.color + self.name

    def __str__(self):
        return "{}({!r}, {!r})".format(
                self.__class__.__name__, to_str_pos(self.pos), self.color)

    def __repr__(self):
        return str(self)

get_x = lambda ip: ip // 16
get_y = lambda ip: ip & 0x0F


class Pawn(ChessPiece):
    name = "P"
    def_cost = 1

    move_vecs = {"W":(0x01, 1), "B":(-0x01, 6)}
    hit_vecs = {"W":(0x11, 0x1 - 0x10), "B":(-0x10 - 0x01, 0x10 - 0x01)}

    def __init__(self, pos, color):
        super(Pawn, self).__init__(pos, color)
        self.move_vec, self.double_move_cell = self.move_vecs[self.color]
        self.hv1, self.hv2 = self.hit_vecs[self.color]

    def get_eq_id(self):
        return (self.name, self.ipos, self.color)

    def get_move_cells(self):
        p1 = self.ipos + self.move_vec
        res = []
        if is_valid_icell(p1):
            res.append(p1)

        if get_y(self.ipos) == self.double_move_cell:
            p1 += self.move_vec 
            if is_valid_icell(p1):
                res.append(p1)
        return [res]

    def get_hit_cells(self):
        p1 = self.ipos + self.hv1
        res = []
        if is_valid_icell(p1):
            res.append([p1])

        p2 = self.ipos + self.hv2
        if is_valid_icell(p2):
            res.append([p2])

        #print self, to_str_pos(self.ipos), "=>", [to_str_pos(i[0]) for i in res]
        return res

    def hit_cells(self):
        res = self.precached_hits.get(self.eq_id)
        if res is None:
            res = self.get_hit_cells()
            self.precached_hits[self.eq_id] = res
        return res


class Knight(ChessPiece):
    name = "N"
    def_cost = 3

    move_diffs = [to_int_pos((dx, dy)) 
                    for dx in (-2, -1, 1, 2) 
                        for dy in (3 - abs(dx), -3 + abs(dx))]

    def get_move_cells(self):
        ip = self.ipos
        ivp = is_valid_icell
        return [[ip + diff] for diff in self.move_diffs if ivp(ip + diff)]


class Bishop(ChessPiece):
    name = "B"
    def_cost = 3

    vects = [0x11, 0x0F, -0x0F, -0x11]
    
    def get_move_cells(self):
        return get_all_iscales(self.ipos, self.vects)


class Rook(ChessPiece):
    name = "R"
    def_cost = 4
    vects = [0x10, -0x10, 0x01, -0x01]

    def get_move_cells(self):
        return get_all_iscales(self.ipos, self.vects)


class Queen(ChessPiece):
    name = "Q"
    def_cost = 8
    vects = Bishop.vects + Rook.vects

    def get_move_cells(self):
        return get_all_iscales(self.ipos, self.vects)


class King(ChessPiece):
    name = "K"    
    def_cost = 1000000

    move_diffs = [to_int_pos((dx, dy)) 
                    for dx in (-1, 0, 1) 
                        for dy in (-1, 0, 1) 
                            if dx * dy != 0]

    def get_move_cells(self):
        return [[self.ipos + diff] 
                    for diff in self.move_diffs 
                        if is_valid_icell(self.ipos + diff)]


def position_evaluate(board):
    return board.sum_cost


def filter_pieces(board, pos, vec, allowed_classes):
    get = board.const_get_func()
    
    dy = get_y(vec)
    dx = get_x(vec)

    for scale in range(1, 8):
        npos = pos + vec * scale

        if get(npos) is not None:
            p = get(npos)
            if scale == 1:
                if isinstance(p, Pawn) and dy != 0:
                    if p.color == "W" and dx == 1:
                        yield p
                    elif p.color == "B" and dx == -1:
                        yield p
                    else:
                        return
                if isinstance(p, King):
                    yield p
                    return
            if isinstance(p, allowed_classes):
                yield p
            else:
                return


def all_pieces_can_hit(board, cell):
    get = board.const_get_func()
    for pos in Knight(cell, "W").hit_cells():
        p = get(pos[0])
        if isinstance(p, Knight):
            yield [p]

    for vec in Bishop.vects:
        l = list(filter_pieces(board, cell, vec, (Queen, Bishop)))
        if l != []:
            yield l

    for vec in Rook.vects:
        l = list(filter_pieces(board, cell, vec, (Queen, Rook)))
        if l != []:
            yield l


def hit_order(board, cell, start_color):
    lists = list(all_pieces_can_hit(board, cell))

    cost = 0
    ccolor = start_color
    cfigure = board.get(cell)
    cost_coef = 1
    while True:
        lists.sort(key=lambda x: x[0].def_cost)
        for l in lists:
            if l[0].color == ccolor:
                cost += cost_coef * getattr(cfigure, "def_cost", 0)
                cfigure = l[0]
                yield l[0], cost
                del l[0]
                break
        else:
            break
        # remove empty lists
        lists = filter(None, lists)
        ccolor = rev_color[ccolor]
        cost_coef = -cost_coef


def get_next_step(board, for_color, level=2):
    moves = None
    best_evaluate = None
    
    cfunc = lambda val: val if for_color == "W" else -val

    for piece in board:
        if piece.color == for_color:
            for mv in board.get_all_moves(piece):
                ppos = piece.ipos
                board.move(piece, mv)

                if level != 1:
                    next_moves, new_val = get_next_step(board, rev_color[for_color], level - 1)
                    new_val = -new_val
                else:
                    new_val = cfunc(position_evaluate(board))
                    next_moves = []

                board.move(piece, ppos)

                if new_val > best_evaluate or best_evaluate is None :
                    best_evaluate = new_val
                    moves = [(piece.ipos, mv)] + next_moves

            for hit in board.get_all_hits(piece):
                
                ppos = piece.ipos
                removed_piece = board.get(hit)

                board.remove(hit)
                board.move(piece, hit)

                if level != 1:
                    next_moves, new_val = get_next_step(board, rev_color[for_color], level - 1)
                    new_val = -new_val
                else:
                    new_val = cfunc(position_evaluate(board))
                    next_moves = []
                
                board.move(piece, ppos)
                board.add(removed_piece)

                if best_evaluate is None or new_val > best_evaluate:
                    best_evaluate = new_val
                    moves = [(piece.ipos, hit)] + next_moves

    return moves, best_evaluate


def knorre_vs_neumann():
    p = [Pawn(i, "B") for i in "A6,B7,C6,C7,G4,H5".split(",")]
    p += [Pawn(i, "W") for i in "A2,B2,C2,E4,H4,G2".split(",")]
    p += [Rook("D1", "W"), Rook("F5", "W"), Rook("G8", "B"), Rook("E8", "B")]
    p += [Knight("G5", "W"), Bishop("G3", "W"), Knight("E5", "B"), Bishop("D6", "B")]    
    return p + [King("B8", "B"), King("H1", "W"), Queen("C3", "W"), Queen("E7", "B")]    

def get_start_board():
    pieces = [Pawn("{}2".format(i), "W") for i in board_letters]
    pieces += [Pawn("{}7".format(i), "B") for i in board_letters]
    pieces += [Bishop("C1", "W"), Bishop("F1", "W")]
    pieces += [Bishop("C8", "B"), Bishop("F8", "B")]
    pieces += [Knight("B1", "W"), Knight("G1", "W")]
    pieces += [Knight("B8", "B"), Knight("G8", "B")]
    pieces += [Rook("A1", "W"), Rook("H1", "W")]
    pieces += [Rook("A8", "B"), Rook("H8", "B")]
    pieces += [Rook("A8", "B"), Rook("H8", "B")]
    pieces += [Queen("E8", "B"), Queen("E1", "W")]
    pieces += [King("D8", "B"), King("D1", "W")]
    return pieces

class Board(object):

    # board is list of pieces
    def __init__(self, pieces):
        self.pieces = pieces
        self.pieces_map = {piece.ipos:piece for piece in self}
        self.sum_cost = sum(piece.cost for piece in pieces)

    def __iter__(self):
        return iter(self.pieces)

    def get_all_moves(self, piece):
        for linked_moves in piece.move_cells():
            for pos in linked_moves:
                if pos in self.pieces_map:
                    break
                yield pos

    def get_all_hits(self, piece):
        get = self.const_get_func()
        for linked_hits in piece.hit_cells():
            
            #print "linked_hits =", map(to_str_pos, linked_hits)

            for pos in linked_hits:
                hited_piece = get(pos)
                #print "get({}) = {!r}".format(to_str_pos(pos), hited_piece)
                if hited_piece is None:
                    continue
                elif hited_piece.color != piece.color:
                    #print "yielding", to_str_pos(pos)
                    yield pos
                break

    def get(self, pos):
        return self.pieces_map.get(pos)

    def const_get_func(self):
        return self.pieces_map.get

    def remove(self, pos):
        piece = self.pieces_map[pos]
        del self.pieces_map[pos]
        self.pieces.remove(piece)
        self.sum_cost -= piece.cost

    def add(self, piece):
        self.sum_cost += piece.cost
        self.pieces.append(piece)
        self.pieces_map[piece.ipos] = piece

    def move(self, piece, pos):
        del self.pieces_map[piece.ipos]
        piece.move(pos)
        self.pieces_map[pos] = piece


import contextlib
@contextlib.contextmanager
def time_it():    
    t = time.time()
    yield
    print time.time() - t

if __name__ == "__main__":
    board = Board(knorre_vs_neumann())

    t = time.time()
    for frm, to in get_next_step(board, "W", 4)[0]:
        print to_str_pos(frm), to_str_pos(to)
    print time.time() - t

    # print "best val =", val
    # for frm, to in moves:
    #     print to_str_pos(frm), to_str_pos(to)

    #for f,c in hit_order(board, to_int_pos("E5"), "W"):
    #    print f, c
