# Wide workspace columns

At viewport widths of 1800px and above, the home workspace places the hero and repository import on the left, and the saved repository list with search on the right. This uses the available width instead of moving unused space from one side to the other. The sidebar inset remains 48px; the two content columns have a 64px gap. Smaller screens keep the stacked layout. Error messages occupy a full-width row without overlapping either column.

Production build passed. Browser measurements at 2560x1440 showed columns of 1196.8px and 979.2px, a 48px sidebar gap, and a repository-list right edge 48px from the viewport. At 1920x1080 the columns were 844.8px and 691.2px. Neither viewport had horizontal overflow. Searching for sampleproject in the right column filtered the saved list correctly; clearing restored it.
