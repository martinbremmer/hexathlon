#!/usr/bin/python

#
# Please be aware that this code uses a lot of brute force loops and random stuff.
# It could be a lot more effecient.
# I'm too lazy to redesign/recode stuff to make it less brute force.
# Anyway, in the state it is now, the code is effecient enough...
#

from __future__ import absolute_import
from __future__ import print_function
import os
import sys
import math
import random
import itertools
import argparse

###############################################################################################################################
# GUI class

import wx
from six.moves import filter
from six.moves import range


class Gui():
    def __init__(self):
        # Initialize wx...
        self._wx = wx.App()
        self._progress = None
        return

    def dialogOpenFile(self, info):
        filename = None
        dialog = wx.FileDialog(None, info, os.getcwd(), "", "*", wx.FD_OPEN | wx.FD_CHANGE_DIR)
        if dialog.ShowModal() == wx.ID_OK:
            filename = dialog.GetPath()
            dialog.Destroy()
        else:
            dialog.Destroy()
            self.dialogExit("No file selected")
        return filename

    def dialogSelectDirectory(self, info):
        dirname = None
        dialog = wx.DirDialog(None, info, os.getcwd(), wx.DD_DEFAULT_STYLE | wx.FD_CHANGE_DIR)
        if dialog.ShowModal() == wx.ID_OK:
            dirname = dialog.GetPath()
            dialog.Destroy()
        else:
            dialog.Destroy()
            self.dialogExit("No directory selected")
        return dirname

    def dialogExit(self, info):
        self.dialogInfo(info+":\nexit!", wx.ICON_ERROR)
        exit(1)

    def dialogInfo(self, info, icon=wx.ICON_INFORMATION):
        dialog = wx.MessageDialog(None, info, "Info", wx.OK | icon)
        dialog.ShowModal()
        dialog.Destroy()
        return

    def dialogProgressStart(self, info):
        assert self._progress is None
        self._progress = wx.ProgressDialog("Progress",
                                           info,
                                           100,
                                           style=wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME)
        return

    def dialogProgressUpdate(self, value, maxValue):
        # Return 'False' when 'Cancel' button was pressed.
        assert self._progress
        percent = value * 100 / maxValue
        result = self._progress.Update(percent)
        return result

    def dialogProgressStop(self):
        assert self._progress
        self._progress.Destroy()
        self._progress = None
        return


###############################################################################################################################
# Data holding element classes

class Game():
    def __init__(self, name):
        assert name
        self._name = name
        return

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self._name == other._name
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def toString(self):
        return "{}".format(self._name)


class Team():
    def __init__(self, name):
        assert name
        self._name = name.split('|', 1)[0]
        self._rank = int(name.rsplit('|', 1)[1])
        return

    def rank(self):
        return self._rank;

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self._name == other._name
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def toString(self):
        #return "{} ({})".format(self._name, self._rank)
        return "{}".format(self._name)


class Pair():
    def __init__(self, t1, t2, rdm=True):
        random.seed()
        if random.random() > 0.5 or rdm is False:
            self._teamA = t1
            self._teamB = t2
        else:
            self._teamA = t2
            self._teamB = t1
        self._scheduled = False

    def toString(self):
        return "[{}] {} -VS- {}".format(self._scheduled, self._teamA.toString(), self._teamB.toString())

    def contains(self, team):
        return team.__eq__(self._teamA) or team.__eq__(self._teamB)

    def overlap(self, pair):
        return self.contains(pair._teamA) or self.contains(pair._teamB)

    def inside(self, pairs):
        for p in pairs:
            if self.overlap(p):
                return True
        return False

    def scheduled(self):
        return self._scheduled

    def available(self, excludeList):
        available = False
        if not self._scheduled:
            available = not self.inside(excludeList)
        return available

    def setScheduled(self, sch):
        self._scheduled = sch
        return

    def getTeams(self):
        return self._teamA, self._teamB


class Match():
    def __init__(self, game):
        assert game
        self._game = game
        self._pair = None
        return

    def addPair(self, pair):
        assert(pair)
        self._pair = pair
        return

    def contains(self, team):
        return self._pair.contains(team)

    def getGame(self):
        return self._game

    def getPair(self):
        return self._pair

    def toString(self):
        if self._pair is None:
            return "Game {}: None -VS- None".format(self._game.toString())
        return "Game {}: {}".format(self._game.toString(), self._pair.toString())




###############################################################################################################################
# Tournament Timeslot parsing and holding class

class Timeslot():
    def __init__(self, time, games, teams, pairs):
        #print("Timeslot({})".format(time), end='')
        self._time = time
        self._teams = list(teams)
        self._recess = []
        self._matches = []
        self._pairs = pairs
        for g in games:
            self._matches.append(Match(g))
        return

    def fill(self, prevSlots):
        assert prevSlots is not None

        # Teams that had a recess previously should play.
        preferredTeams = []
        if len(prevSlots) > 0:
            preferredTeams = list(prevSlots[-1]._recess)

        # Fill in current timeslot.
        slotPairs = []
        for idx, match in enumerate(self._matches):
            # Get all pairs of this game in the previous timeslots
            gamePairs = []
            for s in prevSlots:
                gamePairs.append(s._matches[idx].getPair())

            # Find the pair to add to this game
            preferredTeams = self._filterTeams(preferredTeams, gamePairs)
            preferredTeams = self._filterTeams(preferredTeams, slotPairs)
            pair = self._findPair(gamePairs, slotPairs, preferredTeams)
            if pair is not None:
                # Add this pair to the game/match
                self._matches[idx].addPair(pair)
                # Add this pair to this slots' pairs to exclude it further
                slotPairs.append(pair)
                # This pair is used
                pair.setScheduled(True)
                #print("Match: {}".format(self._matches[idx].toString()))
            else:
                #print("Match: None")
                return False

        # Do all previous recess teams have been scheduled?
        if len(preferredTeams) > 0:
            #print("Timeslot: not all recess teams scheduled")
            #print("-")
            return False

        self._fillRecess()

        return True

    def fillUneven(self, slots, teams):
        assert slots is not None
        assert teams is not None

        for idx, match in enumerate(self._matches):
            # Find last team that has to play this game.
            last = None
            noplay = list(teams)
            for t in teams:
                for s in slots:
                    if s._matches[idx].getPair().contains(t):
                        noplay.remove(t)
            assert len(noplay) == 1
            self._matches[idx].addPair(Pair(noplay[0], Team("-|10"), False))
            #for t in noplay:
            #    print("team: {}".format(t.toString()))
            #print("UnevenMatch: {} ---".format(match.toString()))

        return

    def _findPair(self, excludedPairs1, excludedPairs2, preferredTeams):
        pair = None

        assert excludedPairs1 is not None
        assert excludedPairs2 is not None
        assert preferredTeams is not None

        #print("_findPair {}".format(preferredTeams))

        random.shuffle(self._pairs)

        if len(preferredTeams) == 0:
            pair = self._findPair0(excludedPairs1, excludedPairs2)
        elif len(preferredTeams) == 1:
            pair = self._findPair1(excludedPairs1, excludedPairs2, preferredTeams[0])
            if pair is None:
                pair = self._findPair0(excludedPairs1, excludedPairs2)
        else:
            pair = self._findPairN(excludedPairs1, excludedPairs2, preferredTeams)
            if pair is None:
                for t in preferredTeams:
                    pair = self._findPair1(excludedPairs1, excludedPairs2, t)
                    if pair is not None:
                        break
            if pair is None:
                pair = self._findPair0(excludedPairs1, excludedPairs2)

        return pair

    def _findPair0(self, excludedPairs1, excludedPairs2):
        pair = None
        # Get first non-scheduled pair
        # that is not excluded
        for p in self._pairs:
            if p.available(excludedPairs1) and p.available(excludedPairs2):
                pair = p
        #print("_findPair0 {}".format(pair)
        return pair

    def _findPair1(self, excludedPairs1, excludedPairs2, preferredTeam):
        pair = None
        # Get first non-scheduled pair that contains this single preferred team
        # that is not excluded
        for p in self._pairs:
            if p.available(excludedPairs1) and p.available(excludedPairs2):
                if p.contains(preferredTeam):
                    pair = p
        #print("_findPair1 {}".format(pair))
        return pair

    def _findPairN(self, excludedPairs1, excludedPairs2, preferredTeams):
        pair = None
        # Get first non-scheduled pair that contains preferred teams
        # that is not excluded
        for p in self._pairs:
            if p.available(excludedPairs1) and p.available(excludedPairs2):
                # One preferred team is enough...
                for t in preferredTeams:
                    if p.contains(t):
                        pair = p
        #print("_findPairN {}".format(pair))
        return pair

    def _filterTeams(self, teams, excludedPairs):
        filtered = list(teams)
        # Remove all excluded teams from the preferred list
        for t in teams:
            for e in excludedPairs:
                if e.contains(t):
                    filtered.remove(t)
        random.shuffle(filtered)
        return filtered

    def _fillRecess(self):
        self._recess = list(self._teams)
        for m in self._matches:
            p = m.getPair()
            for t in self._teams:
                if p.contains(t):
                    self._recess.remove(t)
        return

    def teamInRecess(self, team):
        return bool(team in self._recess)

    def recessTeams(self):
        return self._recess

    def getMatches(self):
        return self._matches

    def toString(self):
        return "{}".format(self._time)




###############################################################################################################################
# Tournament calculating, holding and exporting class

boxStyleEnclosed = "\"border-top: 1px solid #000000; border-bottom: 1px solid #000000; border-left: 1px solid #000000; border-right: 1px solid #000000\""
boxStyleOpenTop = "\"border-bottom: 1px solid #000000; border-left: 1px solid #000000; border-right: 1px solid #000000\""
boxStyleOpenBottom  = "\"border-top: 1px solid #000000; border-left: 1px solid #000000; border-right: 1px solid #000000\""
boxStyleOpenVertical  = "\"border-left: 1px solid #000000; border-right: 1px solid #000000\""

class Tournament():
    def __init__(self, games, teams):
        # This only works when we have enough teams to fill all games for every timeslot.
        assert len(games) * 2 <= len(teams)
        random.seed()

        # TODO: remove
        self._calcinfo = []
        self._niceValue = -1

        # Initialize internal information
        self._pairs = []
        self._games = games
        self._teams = teams
        self._timeslots = []
        self._unevenTeams = True
        if len(teams) % 2 == 0:
            self._unevenTeams = False

        # Get all possible pairings
        permutations = list(itertools.combinations(teams, 2))
        for p in permutations:
            self._pairs.append(Pair(p[0], p[1]))
        random.shuffle(self._pairs)

        # Create matrix content
        self._reset()
        self._fillMatrix()
        self._calculateTournamentNiceValue()
        return

    def _fillMatrix(self):
        #
        # Every pair of teams playing a game is a match on a specific timeslot.
        #
        # It is possible that we select all teams in a early timeslot that
        # are the only teams that can play in the current timeslot.
        # It is solvable brute forece, but it could take a while.
        # So, Keep trying to get all matches for this game.
        #
        i = int(0)
        pairs = int(math.floor(len(self._teams) / 2))
        while i < pairs:
            t = Timeslot(i, self._games, self._teams, self._pairs)
            if t.fill(self._timeslots):
                self._timeslots.append(t)
                i += 1
            else:
                self._reset()
                i = 0
        if self._unevenTeams:
            #print("Uneven number of teams.")
            t = Timeslot(len(self._teams) / 2, self._games, self._teams, self._pairs)
            t.fillUneven(self._timeslots, self._teams)
            self._timeslots.append(t)
        return

    def _reset(self):
        print(".", end='')
        sys.stdout.flush()
        random.shuffle(self._pairs)
        for p in self._pairs:
            p.setScheduled(False)
        self._timeslots = []
        self._niceValue = -1
        self._calcinfo = []
        return


    def _calculateTournamentNiceValue(self):
        # The nicest would be that no team has the same oponent ever
        # and it doesn't have successive recesses
        self._niceValue = 0
        for teamAidx in range(len(self._teams)):
            teamA = self._teams[teamAidx]
            #print("Nice for {}".format(teamA.toString()))

            # Get how often this team has successive recesses.
            # We don't care about the last slot. If applicable,
            # then the team is just ready a bit earlier. It just
            # makes it easier when considering uneven number of teams.
            cnt = 0
            tmpValue = 0
            for slotIdx in range(len(self._timeslots) - 1):
                timeslotA = self._timeslots[slotIdx]
                timeslotB = self._timeslots[slotIdx + 1]
                #if timeslotA.teamInRecess(teamA):
                #    print("Pauze for {} in {}".format(teamA.toString(), slotIdx))
                if timeslotA.teamInRecess(teamA) and timeslotB.teamInRecess(teamA):
                    cnt += 1
                    self._calcinfo.append("{}: {} pauze".format(cnt, teamA.toString()))
            if cnt > 0:
                if cnt > 1:
                    cnt = cnt * 3
                tmpValue = 1 << cnt
                tmpValue = tmpValue * 100000 # balance against 'closely matched teams'
            self._niceValue += tmpValue
        niceV1 = self._niceValue

        # Check how closely matched the teams are.
        for timeslot in self._timeslots:
            for match in timeslot.getMatches():
                teamA, teamB = match.getPair().getTeams()
                if teamB is not None:
                    tmpValue = abs(teamA.rank() - teamB.rank())
                    tmpValue = tmpValue * tmpValue * tmpValue;
                    self._niceValue += tmpValue

        self._calcinfo.append("------ {}->{}".format(niceV1, self._niceValue))
        return

    def niceValue(self):
        if self._niceValue < 0:
            self._calculateTournamentNiceValue()
        return self._niceValue

    def niceValueInfo(self):
        if self._niceValue < 0:
            self._calculateTournamentNiceValue()
        for i in self._calcinfo:
            print("{}".format(i))
        return

    def output(self, directory):
        assert directory
        while os.path.exists(directory):
            directory = directory+"_"
        os.makedirs(directory)
        # Create three files:
        #   1) Complete tournament schedule in html.
        #   2) Html document containing score forms for all games.
        #   3) Csv document for import in excel for total tournament scores.
        self._outputTotalSchema(directory)
        self._outputTotalScores(directory)
        self._outputGamesScores(directory)
        return

    def _outputTotalScores(self, directory):
        # |        | Playbackshow | Game 1 | Game 2 | ... | Game N | Red Line | Total                   | | Position |
        # | Team 1 |              |        |        |     |        |          | =(B2*factor)+SUM(C2:n2) | | =RANK(.) |
        # | Team 2 |              |        |        |     |        |          | =(B3*factor)+SUM(C3:n3) | | =RANK(.) |
        #            ^ startCollumn                                  ^ endCollumn
        filename = "{}/totalScores.csv".format(directory)
        startCollumn = ord('B')
        endCollumn = startCollumn
        f = open(filename,'w')
        f.write(",\"Playbackshow\",")
        for game in self._games:
            f.write("\"{}\",".format(game.toString()))
            endCollumn += 1
        f.write("\"Rode Draad\",")
        endCollumn += 1
        f.write("\"Totaal\",,\"Positie\"\n")
        rowIdx = 2
        rowLast = len(self._teams) + 1
        rowFactor = rowLast + 3
        for team in sorted(self._teams, key=lambda Team: Team.toString().lower()):
            f.write("\"{}\",".format(team.toString()))
            for col in range(startCollumn, endCollumn + 1):
                f.write(",")
            f.write("\"=(B{}*B{})+SUM(C{}:{}{})\",".format(rowIdx, rowFactor, rowIdx, chr(endCollumn), rowIdx))
            f.write(",")
            f.write("\"=RANK({}{},${}$2:${}{},0)\"\n".format(chr(endCollumn+1), rowIdx, chr(endCollumn+1), chr(endCollumn+1), rowLast))
            rowIdx += 1
        f.write("\n\n")
        f.write("\"Factor\",\"0.7\",\"Playbackshow punten deel factor (max punten is 90)\"\n")
        f.close()
        return

    def _outputTotalSchema(self, directory):
        filename = "{}/totalSchema.html".format(directory)
        f = open(filename,'w')
        self._outputHtmlHead(f, "Tournament schedule")
        for timeslot in self._timeslots:
            matchFirst = timeslot.getMatches()[0]
            matchLast  = timeslot.getMatches()[-1]
            # Table head
            f.write("<TABLE CELLSPACING=\"0\" COLS=\"4\" BORDER=\"0\">\n")
            f.write("   <COLGROUP WIDTH=\"50\"></COLGROUP>\n")
            f.write("   <COLGROUP WIDTH=\"200\"></COLGROUP>\n")
            f.write("   <COLGROUP WIDTH=\"175\"></COLGROUP>\n")
            f.write("   <COLGROUP WIDTH=\"175\"></COLGROUP>\n")
            # Matches meta info
            f.write("   <TR>\n")
            f.write("      <TD STYLE={} HEIGHT=\"20\" ALIGN=\"LEFT\" VALIGN=MIDDLE><B><I>TIJD</I></B></TD>\n".format(boxStyleEnclosed))
            f.write("      <TD STYLE={} ALIGN=\"LEFT\" VALIGN=MIDDLE><B><I>SPEL</I></B></TD>\n".format(boxStyleEnclosed))
            f.write("      <TD STYLE={} ALIGN=\"LEFT\" VALIGN=MIDDLE><B><I>TEAM 1</I></B></TD>\n".format(boxStyleEnclosed))
            f.write("      <TD STYLE={} ALIGN=\"LEFT\" VALIGN=MIDDLE><B><I>TEAM 2</I></B></TD>\n".format(boxStyleEnclosed))
            f.write("   </TR>\n")
            for match in timeslot.getMatches():
                # Determine table cell style
                leftBoxStyle = boxStyleOpenVertical
                if match is matchFirst:
                    # First row: left box is only open at the bottom.
                    leftBoxStyle = boxStyleOpenBottom
                elif match is matchLast:
                    # Last row: left box is only open at the top.
                    leftBoxStyle = boxStyleOpenTop
                # Get teams
                teamA, teamB = match.getPair().getTeams()
                if teamB is None:
                    teamB = "----"
                else:
                    teamB = teamB.toString()
                teamA = teamA.toString()
                # Print match info.
                f.write("   <TR>\n")
                f.write("      <TD STYLE={} HEIGHT=\"20\" ALIGN=\"LEFT\"><BR></TD>\n".format(leftBoxStyle))
                f.write("      <TD STYLE={} ALIGN=\"LEFT\" VALIGN=MIDDLE>{}</TD>\n".format(boxStyleEnclosed, match.getGame().toString()))
                f.write("      <TD STYLE={} ALIGN=\"LEFT\" VALIGN=MIDDLE>{}</TD>\n".format(boxStyleEnclosed, teamA))
                f.write("      <TD STYLE={} ALIGN=\"LEFT\" VALIGN=MIDDLE>{}</TD>\n".format(boxStyleEnclosed, teamB))
                f.write("   </TR>\n")
            # Table tail
            f.write("</TABLE>\n")
            f.write("<BR>\n")
            # Add a page break every now and then.
            position = self._timeslots.index(timeslot) + 1
            if (position % 5) == 0:
                f.write("<p style=\"page-break-before: always\"><!-- NEXT PAGE --></p>\n")
        self._outputHtmlTail(f)
        f.close()
        return


    def _outputGamesScores(self, directory):
        filename = "{}/gamesScores.html".format(directory)
        f = open(filename,'w')
        self._outputHtmlHead(f, "Games scores")
        for game in self._games:
            # Table head
            f.write("<TABLE CELLSPACING=\"0\" COLS=\"4\" BORDER=\"0\">\n")
            f.write("   <COLGROUP WIDTH=\"75\"></COLGROUP>\n")
            f.write("   <COLGROUP WIDTH=\"275\"></COLGROUP>\n")
            f.write("   <COLGROUP WIDTH=\"125\"></COLGROUP>\n")
            f.write("   <COLGROUP WIDTH=\"125\"></COLGROUP>\n")
            # Game meta info
            f.write("   <TR>\n")
            f.write("      <TD HEIGHT=\"25\" ALIGN=\"LEFT\"><B><I><FONT SIZE=4>SPEL</FONT></I></B></TD>\n")
            f.write("      <TD ALIGN=\"LEFT\"><B><I><FONT SIZE=4>{}</FONT></I></B></TD>\n".format(game.toString()))
            f.write("      <TD ALIGN=\"LEFT\"><BR></TD>\n")
            f.write("      <TD ALIGN=\"LEFT\"><BR></TD>\n")
            f.write("   </TR>\n")
            f.write("   <TR><TD HEIGHT=\"10\"><BR></TD><TD><BR></TD><TD><BR></TD><TD><BR></TD></TR>\n")
            f.write("   <TR>\n")
            f.write("      <TD STYLE={} HEIGHT=\"25\" ALIGN=\"LEFT\"><B><I><FONT SIZE=4>TIJD</FONT></I></B></TD>\n".format(boxStyleEnclosed))
            f.write("      <TD STYLE={} ALIGN=\"LEFT\"><B><I><FONT SIZE=4>TEAMS</FONT></I></B></TD>\n".format(boxStyleEnclosed))
            f.write("      <TD STYLE={} ALIGN=\"LEFT\"><B><I><FONT SIZE=4>SCORE</FONT></I></B></TD>\n".format(boxStyleEnclosed))
            f.write("      <TD STYLE={} ALIGN=\"LEFT\"><B><I><FONT SIZE=4>PUNTEN</FONT></I></B></TD>\n".format(boxStyleEnclosed))
            f.write("   </TR>\n")
            f.write("   <TR><TD HEIGHT=\"10\"><BR></TD><TD><BR></TD><TD><BR></TD><TD><BR></TD></TR>\n")
            # Game matches
            for timeslot in self._timeslots:
                for match in timeslot.getMatches():
                    if match.getGame() is game:
                        # MatchDummy info.
                        teamA, teamB = match.getPair().getTeams()
                        if teamB is None:
                            teamB = "----"
                        else:
                            teamB = teamB.toString()
                        teamA = teamA.toString()
                        f.write("   <TR>\n")
                        f.write("      <TD STYLE={} HEIGHT=\"30\" ALIGN=\"LEFT\"><BR></TD>\n".format(boxStyleOpenBottom))
                        f.write("      <TD STYLE={} ALIGN=\"LEFT\" VALIGN=MIDDLE><FONT SIZE=4>{}</FONT></TD>\n".format(boxStyleEnclosed, teamA))
                        f.write("      <TD STYLE={} ALIGN=\"LEFT\"><BR></TD>\n".format(boxStyleEnclosed))
                        f.write("      <TD STYLE={} ALIGN=\"LEFT\"><BR></TD>\n".format(boxStyleEnclosed))
                        f.write("   </TR>\n")
                        f.write("   <TR>\n")
                        f.write("      <TD STYLE={} HEIGHT=\"30\" ALIGN=\"LEFT\"><BR></TD>\n".format(boxStyleOpenTop))
                        f.write("      <TD STYLE={} ALIGN=\"LEFT\" VALIGN=MIDDLE><FONT SIZE=4>{}</FONT></TD>\n".format(boxStyleEnclosed, teamB))
                        f.write("      <TD STYLE={} ALIGN=\"LEFT\"><BR></TD>\n".format(boxStyleEnclosed))
                        f.write("      <TD STYLE={} ALIGN=\"LEFT\"><BR></TD>\n".format(boxStyleEnclosed))
                        f.write("   </TR>\n")
                        f.write("   <TR><TD HEIGHT=\"10\"><BR></TD><TD><BR></TD><TD><BR></TD><TD><BR></TD></TR>\n")
            # Table tail
            f.write("</TABLE>\n")
            if game is not self._games[-1]:
                f.write("<p style=\"page-break-before: always\"><!-- NEXT PAGE --></p>\n")
        self._outputHtmlTail(f)
        f.close()
        return

    def _outputHtmlHead(self, f, title):
        f.write("<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 3.2//EN\">\n")
        f.write("<HTML>\n")
        f.write("<HEAD>\n")
        f.write("   <TITLE>{}</TITLE>\n".format(title))
        f.write("   <META NAME=\"GENERATOR\" CONTENT=\"GamesSchemaGenerator\" CHARSET=\"utf-8\">\n")
        f.write("   <STYLE>\n")
        f.write("      <!--\n")
        f.write("      BODY,DIV,TABLE,THEAD,TBODY,TFOOT,TR,TH,TD,P { font-family:\"Arial\"; font-size:x-small }\n")
        f.write("      -->\n")
        f.write("   </STYLE>\n")
        f.write("</HEAD>\n")
        f.write("<BODY TEXT=\"#000000\">\n")
        return

    def _outputHtmlTail(self, f):
        f.write("</BODY>\n\n")
        f.write("</HTML>\n")
        return

    def display(self):
        for row in self._matches:
            for match in row:
                print(match.toString())
        print("Nice: {}".format(self.niceValue()))
        return









###############################################################################################################################
# Support functions

def readLineFile(filename):
    lines = []
    f = open(filename,'r')
    content = f.read()
    f.close()
    if content is not None:
        lines = content.split('\n')
    lines = [s.strip() for s in lines]
    lines = list(filter(len, lines))
    return lines


def main():
    games = []
    teams = []
    gui = Gui()

    parser = argparse.ArgumentParser()
    parser.add_argument('--teams',  type=int, help='Number of teams.')
    parser.add_argument('--games',  type=int, help='Number of games.')
    parser.add_argument('--output', type=str, help='Directory to put the results into.')

    args = parser.parse_args()

    # Ask user to open files, then read them into arrays.
    # or just generate the games and teams lists.
    lines = []
    if args.games is not None:
        for i in range(0, args.games):
            lines.append("Game{}".format(i+1))
    else:
        gui.dialogInfo("Open file containing games")
        filenameGames = gui.dialogOpenFile("Open file containing games")
        lines = readLineFile(filenameGames)
    for line in lines:
        game = Game(line)
        if game in games:
            gui.dialogExit("Two games with the same name")
        games.append(game)
        filenameTeams = None
    lines = []
    if args.teams is not None:
        for i in range(0, args.teams):
            lines.append("Team{}|{}".format(i+1, i+1))
    else:
        gui.dialogInfo("Open file containing teams")
        filenameTeams = gui.dialogOpenFile("Open file containing teams")
        lines = readLineFile(filenameTeams)
    for line in lines:
        team = Team(line)
        if team in teams:
            gui.dialogExit("Two teams with the same name")
        teams.append(team)

    # This only works when we have enough teams to fill all games for every timeslot.
    if len(games) * 2 > len(teams):
        gui.dialogExit("This only works if you have at least twice the number of teams compared to the number of games")

    # Some nice info
    print("Generate for {} teams...".format(len(teams)))
    # for t in teams:
    #     print("Team: {}".format(t.toString()))
    # for g in games:
    #     print("Game: {}".format(g.toString()))

    # Create tournament
    tournament = None
    nicest = Tournament(games, teams)
    cnt = 0
    while nicest.niceValue() > 0 and cnt < 10:
        tournament = Tournament(games, teams)
        if tournament.niceValue() < nicest.niceValue():
            nicest = tournament
            cnt = 0
        cnt += 1
        print("({}){}/{}".format(cnt, tournament.niceValue(), nicest.niceValue()))
        sys.stdout.flush()
    tournament = nicest
    print("")
    tournament.niceValueInfo()

    # Create output files
    dirname = None
    if args.output is not None:
        dirname = "{}/{}/{}".format(args.output, len(teams), tournament.niceValue())
    else:
        gui.dialogInfo("Select Tournament output directory...")
        dirname = gui.dialogSelectDirectory("Open output directory")
    tournament.output(dirname)

    return


if __name__ == "__main__":
    main()

